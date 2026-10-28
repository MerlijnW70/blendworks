import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes

judge_dir, folder = sys.argv[1], sys.argv[2]
sys.path.insert(0, judge_dir)

from judge_common import SHARED_ACCESS_SECONDS, FileLockError, read_bytes, shared_access, write_json

GENERIC_READ = 0x80000000
OPEN_ALWAYS = 4
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateFileW.restype = wintypes.HANDLE
kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]


def hold(path, seconds):
    handle = kernel.CreateFileW(path, GENERIC_READ, 0, None, OPEN_ALWAYS, 0x80, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "could not hold the file")
    threading.Timer(seconds, lambda: kernel.CloseHandle(handle)).start()


def timed(action):
    started = time.monotonic()
    try:
        action()
        return {"ok": True, "seconds": round(time.monotonic() - started, 3)}
    except PermissionError as error:
        return {"ok": False, "seconds": round(time.monotonic() - started, 3), "error": str(error)}
    except FileLockError as error:
        return {"ok": False, "seconds": round(time.monotonic() - started, 3), "error": error.code}


def append(path):
    def write():
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("line\n")

    return write


def case(name, held, action, seconds=0.3):
    path = os.path.join(folder, name)
    hold(path + held, seconds)
    return timed(lambda: action(path))


result = {
    "bound": SHARED_ACCESS_SECONDS,
    "replace": case("replace.json", "", lambda path: write_json(path, {"ok": True})),
    "create": case("create.json", ".partial", lambda path: write_json(path, {"ok": True})),
    "read": case("read.json", "", lambda path: read_bytes(path)),
    "append": case("progress.log", "", lambda path: shared_access(append(path))),
    "plain": case("plain.log", "", lambda path: append(path)()),
    "bounded": case("bounded.json", "", lambda path: write_json(path, {"ok": True}), seconds=SHARED_ACCESS_SECONDS + 2.0),
}
time.sleep(SHARED_ACCESS_SECONDS + 2.5)
with open(os.path.join(folder, "probe.json"), "w", encoding="utf-8") as handle:
    json.dump(result, handle)
