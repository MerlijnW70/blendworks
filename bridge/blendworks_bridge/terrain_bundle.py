"""Selects the prebuilt native terrain core for the running platform and checks its sha256 against the release manifest."""

import hashlib
import json
import platform
import sys
from pathlib import Path

MANIFEST_NAME = "manifest.json"
PLATFORMS = ("win32-x64", "linux-x64", "darwin-arm64", "darwin-x64")
ARCHITECTURES = {"amd64": "x64", "x86_64": "x64", "x64": "x64", "arm64": "arm64", "aarch64": "arm64"}
SYSTEMS = {"win32": "win32", "linux": "linux", "darwin": "darwin"}
SLOWDOWN = "the Python reference kernels run roughly 100 times slower than the native core"


def platform_key(system=None, machine=None):
    system = sys.platform if system is None else system
    machine = platform.machine() if machine is None else machine
    name = "win32" if system.startswith("win") else SYSTEMS.get(system.split("-")[0])
    arch = ARCHITECTURES.get(machine.lower())
    key = f"{name}-{arch}" if name and arch else None
    return key if key in PLATFORMS else None


def bundled_roots():
    here = Path(__file__).resolve()
    return [here.parent / "native", here.parents[2] / "native" / "dist"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_manifest(root):
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) and isinstance(manifest.get("files"), dict) else None


def verdict(check, reason=None, path=None, data=None, expected=None, actual=None):
    return {"check": check, "reason": reason, "path": path, "data": data, "expected": expected, "actual": actual}


def select(key=None, roots=None):
    key = platform_key() if key is None else key
    if key is None:
        return verdict("missing", f"no prebuilt native core exists for {sys.platform} on {platform.machine()}; supported are {', '.join(PLATFORMS)}")
    for root in bundled_roots() if roots is None else roots:
        manifest = read_manifest(root)
        entry = manifest["files"].get(key) if manifest else None
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str) or not isinstance(entry.get("sha256"), str):
            continue
        path = root / key / entry["file"]
        try:
            data = path.read_bytes()
        except OSError:
            return verdict("missing", f"the manifest at {root} lists {key} but {path} cannot be read", str(path))
        actual = digest(data)
        if actual != entry["sha256"].lower():
            return verdict("mismatched", f"the bundled native core {path} has sha256 {actual} but the manifest says {entry['sha256']}; refusing it", str(path), None, entry["sha256"], actual)
        return verdict("loaded", None, str(path), data, actual, actual)
    return verdict("missing", f"no prebuilt native core for {key} is bundled with this install")
