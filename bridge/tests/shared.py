"""Run several bridge test files in one Blender process, with a full reset between them.

Usage: blender --background --factory-startup --python bridge/tests/shared.py -- <test file> ...

Before each file the reset restores Blender's factory settings and data, drops every module
loaded from bridge/, and puts sys.path, os.environ, the working directory and the numpy and
warnings settings back as they were when the process started. After each file the reset runs
again and a fingerprint of the state that the reset cannot restore (persistent handlers,
registered classes, enabled add-ons, threads, logging handlers, driver namespace, data blocks)
is compared with the fingerprint taken at the start. A process that holds more than RECYCLE_MB
of resident memory after a reset stops, so that the memory Blender keeps after big files is given
back, and the files after it run in a new process. Factory settings register the handlers of
Blender's bundled add-ons (pose_library) once more on every reset, the same function objects; the
reset drops those repeats, since a fresh process has each of them once. numpy is imported before
the start so that its settings are part of the baseline. Any difference is a leak: the file fails
with the difference named, and the process stops so that no later file runs after it.

Each file is announced on stdout with a line starting with BLENDWORKS-SHARED and a JSON object:
{"event": "start", "file": ...} and {"event": "end", "file": ..., "passed": ..., "seconds": ...,
"leaks": [...]}. A file passes when it runs to its end, or exits with code 0, without a leak.
"""

import gc
import json
import logging
import os
import runpy
import sys
import threading
import time
import traceback
import warnings

import bpy

MARK = "BLENDWORKS-SHARED "
BRIDGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_BLOCKS = (
    "actions", "armatures", "brushes", "cameras", "collections", "curves", "fonts", "grease_pencils", "images", "lattices",
    "libraries", "lights", "linestyles", "masks", "materials", "meshes", "metaballs", "movieclips", "node_groups", "objects",
    "paint_curves", "palettes", "particles", "pointclouds", "scenes", "screens", "sounds", "speakers", "texts", "textures",
    "volumes", "window_managers", "workspaces", "worlds",
)


def emit(event):
    sys.stdout.flush()
    sys.stdout.write(MARK + json.dumps(event) + "\n")
    sys.stdout.flush()


def bridge_module(module):
    path = getattr(module, "__file__", None)
    if not isinstance(path, str):
        return False
    try:
        return os.path.commonpath([os.path.abspath(path), BRIDGE]) == BRIDGE
    except ValueError:
        return False


def numpy_settings():
    numpy = sys.modules.get("numpy")
    if numpy is None:
        return None
    return {"err": numpy.geterr(), "print": numpy.get_printoptions()}


class Baseline:
    def __init__(self):
        self.path = list(sys.path)
        self.environ = dict(os.environ)
        self.cwd = os.getcwd()
        self.warnings = list(warnings.filters)
        self.numpy = numpy_settings()
        self.handlers = {name: list(handlers) for name, handlers in handler_lists().items()}

    def drop_repeated_handlers(self):
        for name, handlers in handler_lists().items():
            allowed = {}
            for handler in self.handlers.get(name, []):
                allowed[id(handler)] = allowed.get(id(handler), 0) + 1
            seen = {}
            for handler in list(handlers):
                if id(handler) not in allowed:
                    continue
                seen[id(handler)] = seen.get(id(handler), 0) + 1
                if seen[id(handler)] > allowed[id(handler)]:
                    handlers.remove(handler)

    def restore(self):
        self.drop_repeated_handlers()
        for name in [name for name, module in list(sys.modules.items()) if bridge_module(module) and name != __name__]:
            del sys.modules[name]
        sys.path[:] = self.path
        if dict(os.environ) != self.environ:
            os.environ.clear()
            os.environ.update(self.environ)
        os.chdir(self.cwd)
        warnings.filters[:] = self.warnings
        numpy = sys.modules.get("numpy")
        if numpy is not None and self.numpy is not None:
            numpy.seterr(**self.numpy["err"])
            numpy.set_printoptions(**self.numpy["print"])


def full_reset(baseline):
    bpy.ops.wm.read_factory_settings(use_empty=False)
    baseline.restore()
    gc.collect()


def handler_lists():
    return {name: getattr(bpy.app.handlers, name) for name in dir(bpy.app.handlers) if isinstance(getattr(bpy.app.handlers, name), list)}


def handler_counts():
    return {name: sorted(f"{getattr(handler, '__module__', '?')}.{getattr(handler, '__qualname__', repr(handler))}" for handler in handlers) for name, handlers in handler_lists().items()}


def registered_classes():
    found = set()
    stack = list(bpy.types.bpy_struct.__subclasses__())
    seen = set()
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
        if cls.__module__ != "bpy.types" and getattr(cls, "is_registered", False):
            found.add(f"{cls.__module__}.{cls.__qualname__}")
    return sorted(found)


def fingerprint():
    return {
        "data": {name: sorted(block.name for block in getattr(bpy.data, name)) for name in DATA_BLOCKS if hasattr(bpy.data, name)},
        "handlers": handler_counts(),
        "types": sorted(dir(bpy.types)),
        "classes": registered_classes(),
        "addons": sorted(bpy.context.preferences.addons.keys()),
        "threads": sorted(thread.name for thread in threading.enumerate()),
        "logging": [repr(handler) for handler in logging.getLogger().handlers],
        "driver_namespace": sorted(bpy.app.driver_namespace.keys()),
        "bridge_modules": sorted(name for name, module in sys.modules.items() if bridge_module(module) and name != __name__),
        "numpy": repr(numpy_settings()),
        "scene": {
            "engine": bpy.context.scene.render.engine,
            "frame": bpy.context.scene.frame_current,
            "fps": bpy.context.scene.render.fps,
            "unit_scale": bpy.context.scene.unit_settings.scale_length,
        },
    }


def differences(before, after, prefix=""):
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(set(before) | set(after), key=str):
            out.extend(differences(before.get(key), after.get(key), f"{prefix}{key}."))
        return out
    if before == after:
        return []
    if isinstance(before, list) and isinstance(after, list):
        added = list(after)
        removed = []
        for item in before:
            if item in added:
                added.remove(item)
            else:
                removed.append(item)
        parts = ([f"added {added[:5]}"] if added else []) + ([f"removed {removed[:5]}"] if removed else [])
        return [f"{prefix.rstrip('.')}: {', '.join(parts) or 'reordered'}"]
    return [f"{prefix.rstrip('.')}: {before!r} -> {after!r}"]


def run_file(path):
    started = time.perf_counter()
    passed = True
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as stop:
        passed = stop.code in (None, 0)
        if not passed:
            print(f"the file exited with {stop.code!r}")
    except BaseException:
        passed = False
        traceback.print_exc(file=sys.stdout)
    return passed, time.perf_counter() - started


def files_from_argv(argv):
    return argv[argv.index("--") + 1:] if "--" in argv else []


RECYCLE_MB = float(os.environ.get("BLENDWORKS_SHARED_RECYCLE_MB") or 1024)


def resident_mb():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD), ("peak", ctypes.c_size_t), ("working", ctypes.c_size_t)] + [(f"more{i}", ctypes.c_size_t) for i in range(6)]

        counters = Counters()
        counters.size = ctypes.sizeof(counters)
        kernel, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.size)
        return counters.working / (1024 * 1024)
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return 0
    return 0


def main(files):
    baseline = Baseline()
    full_reset(baseline)
    clean = fingerprint()
    for path in files:
        emit({"event": "start", "file": os.path.basename(path)})
        passed, seconds = run_file(path)
        sys.stdout.flush()
        try:
            full_reset(baseline)
            leaks = differences(clean, fingerprint())
        except BaseException:
            traceback.print_exc(file=sys.stdout)
            leaks = ["the reset after the file failed"]
        for leak in leaks:
            print(f"leaked state: {leak}")
        emit({"event": "end", "file": os.path.basename(path), "passed": passed and not leaks, "seconds": round(seconds, 3), "leaks": leaks})
        if leaks:
            return
        if resident_mb() > RECYCLE_MB:
            print(f"this process holds {resident_mb():.0f} MB after the reset, more than {RECYCLE_MB:.0f} MB; the files after it run in a new process")
            return


if __name__ == "__main__":
    import numpy

    main(files_from_argv(sys.argv))
