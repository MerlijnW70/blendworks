"""Journal files of the autosave: line encoding, hashes and change detection."""

import hashlib
import json
import os
import sys

from .workspace import Workspace

FORMAT = 1
HASH_CHUNK = 4 * 1024 * 1024
READ_FLAGS_MASK = os.O_WRONLY | os.O_RDWR | getattr(os, "O_APPEND", 0) | getattr(os, "O_CREAT", 0) | getattr(os, "O_TRUNC", 0)


def journal_name(generation):
    return f"journal-{generation}.jsonl"


def encode_line(value):
    return (json.dumps(value, allow_nan=False, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


class FileHashes:
    def __init__(self):
        self.known = {}

    def describe(self, path):
        stat = os.stat(path)
        cached = self.known.get(path)
        if cached is not None and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
            digest = cached[2]
        else:
            digest = sha256_of(path)
            self.known[path] = (stat.st_size, stat.st_mtime_ns, digest)
        return {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest}


def stat_changed(path, size, mtime_ns):
    try:
        stat = os.stat(path)
    except OSError:
        return True
    return stat.st_size != size or stat.st_mtime_ns != mtime_ns


def content_changed(path, size, sha256):
    try:
        if os.path.getsize(path) != size:
            return True
        return sha256_of(path) != sha256
    except OSError:
        return True


class JournalFile:
    def __init__(self, path, generation):
        self.path = path
        self.generation = generation
        self.bytes = 0

    @staticmethod
    def create(path, generation, entries=(), atomic=False):
        written = f"{path}.partial" if atomic else path
        with open(written, "wb") as handle:
            handle.write(encode_line({"journal": FORMAT, "generation": generation}))
            for entry in entries:
                handle.write(encode_line(entry))
        if atomic:
            os.replace(written, path)
        return JournalFile(path, generation)

    def open(self):
        self.bytes = os.path.getsize(self.path)
        return self

    def append(self, line):
        try:
            with open(self.path, "ab") as handle:
                self.write(handle, line)
        except OSError:
            self.drop_partial_line()
            raise
        self.bytes += len(line)

    @staticmethod
    def write(handle, line):
        handle.write(line)

    def drop_partial_line(self):
        try:
            os.truncate(self.path, self.bytes)
        except OSError:
            pass


def read_journal(path, generation):
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        return None, f"the journal could not be read: {error}"
    lines = data.split(b"\n")
    torn = lines[-1] != b""
    lines = lines[:-1]
    try:
        header = json.loads(lines[0].decode("utf-8")) if lines else None
    except (UnicodeDecodeError, ValueError):
        header = None
    if not isinstance(header, dict) or header.get("journal") != FORMAT or header.get("generation") != generation:
        return None, "the journal header does not match the snapshot"
    entries = []
    for index, raw in enumerate(lines[1:], start=1):
        try:
            entry = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None, f"journal line {index + 1} is not readable"
        if not isinstance(entry, dict) or not isinstance(entry.get("cmd"), str):
            return None, f"journal line {index + 1} is not a request"
        entries.append(entry)
    return {"entries": entries, "torn": torn}, None


class ReadRecorder:
    active = None
    installed = False

    def __init__(self, root, excluded):
        self.root = os.path.normcase(root)
        self.excluded = os.path.normcase(excluded)
        self.paths = []
        self.seen = set()

    def __enter__(self):
        if not ReadRecorder.installed:
            sys.addaudithook(audit_open)
            ReadRecorder.installed = True
        ReadRecorder.active = self
        return self

    def __exit__(self, *details):
        ReadRecorder.active = None
        return False

    def note(self, path):
        try:
            resolved = os.path.realpath(os.path.abspath(os.fsdecode(path)))
        except (TypeError, ValueError, OSError):
            return
        key = os.path.normcase(resolved)
        if key in self.seen or not inside(key, self.root) or inside(key, self.excluded):
            return
        if os.path.isfile(resolved):
            self.seen.add(key)
            self.paths.append(resolved)


def inside(path, folder):
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


def reads_only(mode, flags):
    if isinstance(mode, str):
        return not any(letter in mode for letter in "wax+")
    return isinstance(flags, int) and flags & READ_FLAGS_MASK == 0


def audit_open(event, args):
    recorder = ReadRecorder.active
    if recorder is None or event != "open" or len(args) < 3:
        return
    path, mode, flags = args[0], args[1], args[2]
    if isinstance(path, int) or path is None or not reads_only(mode, flags):
        return
    recorder.note(path)


class RecordingWorkspace(Workspace):
    def __init__(self, workspace, recorder):
        self.root = workspace.root
        self.recorder = recorder

    def existing(self, path, extensions):
        resolved = super().existing(path, extensions)
        self.recorder.note(resolved)
        return resolved
