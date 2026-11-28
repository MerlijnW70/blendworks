"""Loader of the native terrain core: finds and loads the library through ctypes, describes numpy buffers, falls back with one stated reason."""

import ctypes
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import numpy

from . import terrain_bundle

LIBRARY_VARIABLE = "BLENDWORKS_NATIVE_LIB"
REQUIRE_VARIABLE = "BLENDWORKS_NATIVE"
REQUIRED_MARKER = Path("/etc/blendworks/native-required")
ABI_VERSION = 2
KIND_FLOAT64 = 1
KIND_INT32 = 3
KINDS = {numpy.dtype(numpy.float64): KIND_FLOAT64, numpy.dtype(numpy.int32): KIND_INT32}
ERROR_NAMES = {1: "invalid argument", 2: "flow graph cycle", 3: "internal error"}


class NativeError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{ERROR_NAMES.get(code, f'error {code}')}: {message}")
        self.code = code
        self.detail = message


class CoreMissing(RuntimeError):
    pass


class Buffer(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("len", ctypes.c_uint64), ("kind", ctypes.c_uint32), ("item_size", ctypes.c_uint32), ("contiguous", ctypes.c_uint32), ("writable", ctypes.c_uint32)]


class GridSpec(ctypes.Structure):
    _fields_ = [("rows", ctypes.c_int64), ("columns", ctypes.c_int64), ("spacing_x", ctypes.c_double), ("spacing_y", ctypes.c_double), ("edges", ctypes.c_int64)]


BUFFER = ctypes.POINTER(Buffer)
GRID = ctypes.POINTER(GridSpec)
I64 = ctypes.c_int64
F64 = ctypes.c_double
OUT = ctypes.POINTER(ctypes.c_int64)
SIGNATURES = {
    "bw_d8": [GRID, I64, BUFFER, BUFFER, OUT],
    "bw_mfd": [GRID, I64, BUFFER, F64, BUFFER, BUFFER, OUT],
    "bw_order": [GRID, I64, BUFFER, I64, BUFFER, BUFFER, BUFFER, BUFFER, OUT],
    "bw_accumulate": [GRID, I64, I64, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER],
    "bw_incise": [GRID, I64, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, F64, F64, F64, BUFFER],
    "bw_route_lakes": [GRID, I64, BUFFER, BUFFER, BUFFER, BUFFER, I64, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, BUFFER, OUT, OUT],
    "bw_priority_flood": [GRID, BUFFER, I64, BUFFER, OUT],
    "bw_diffuse": [GRID, I64, BUFFER, BUFFER, F64, F64, F64, I64, BUFFER],
    "bw_slide": [GRID, I64, BUFFER, BUFFER, F64, I64, BUFFER],
}


def describe(array):
    array = numpy.asarray(array)
    found = Buffer(array.ctypes.data if array.size else None, array.size, KINDS.get(array.dtype, 0), array.dtype.itemsize, int(array.flags.c_contiguous), int(array.flags.writeable))
    found.owner = array
    return found


def grid_spec(grid):
    return GridSpec(grid.rows, grid.columns, grid.spacing_x, grid.spacing_y, grid.edges)


def library_name(platform=sys.platform):
    if platform.startswith("win"):
        return "blendworks_core.dll"
    if platform == "darwin":
        return "libblendworks_core.dylib"
    return "libblendworks_core.so"


def default_path():
    return Path(__file__).resolve().parents[2] / "native" / "target" / "release" / library_name()


def configured_path(environ=os.environ):
    given = environ.get(LIBRARY_VARIABLE, "").strip()
    return Path(given) if given else default_path()


def required(environ=None, marker=None):
    environ = os.environ if environ is None else environ
    marker = MARKER["path"] if marker is None else marker
    return environ.get(REQUIRE_VARIABLE, "").strip().lower() == "require" or marker.is_file()


def loadable_copy(path, data=None):
    if os.name != "nt":
        return path
    data = path.read_bytes() if data is None else data
    folder = Path(tempfile.gettempdir()) / "blendworks-native"
    target = folder / f"{path.stem}-{hashlib.sha256(data).hexdigest()[:20]}{path.suffix}"
    if not target.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        partial = folder / f"{target.name}.{os.getpid()}.part"
        partial.write_bytes(data)
        os.replace(partial, target)
    return target


class Core:
    def __init__(self, handle, path):
        self.handle = handle
        self.path = path
        self.functions = {}
        for name, argtypes in SIGNATURES.items():
            function = getattr(handle, name)
            function.argtypes = argtypes
            function.restype = ctypes.c_int32
            self.functions[name] = function
        handle.bw_last_error.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
        handle.bw_last_error.restype = ctypes.c_uint64

    def last_error(self):
        size = int(self.handle.bw_last_error(None, 0))
        text = ctypes.create_string_buffer(size + 1)
        self.handle.bw_last_error(text, size + 1)
        return text.value.decode("utf-8", "replace")

    def call(self, name, *arguments):
        prepared = [ctypes.byref(argument) if isinstance(argument, (Buffer, GridSpec, ctypes.c_int64)) else argument for argument in arguments]
        code = self.functions[name](*prepared)
        if code != 0:
            raise NativeError(code, self.last_error())


def load(path=None, data=None):
    path = Path(path) if path is not None else configured_path()
    if not path.is_file():
        return None, f"no native core at {path}; build it with npm run build"
    try:
        handle = ctypes.CDLL(str(loadable_copy(path, data)))
    except OSError as error:
        return None, f"the native core at {path} failed to load: {error}"
    try:
        handle.bw_abi_version.restype = ctypes.c_uint32
        version = int(handle.bw_abi_version())
        if version != ABI_VERSION:
            return None, f"the native core at {path} has ABI version {version}, the bridge needs {ABI_VERSION}; rebuild it with npm run build"
        return Core(handle, path), None
    except AttributeError as error:
        return None, f"the native core at {path} lacks a function: {error}"


STATE = {}
MARKER = {"path": REQUIRED_MARKER}


def locate(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get(LIBRARY_VARIABLE, "").strip():
        return "environment", terrain_bundle.verdict("loaded", None, environ[LIBRARY_VARIABLE].strip())
    if default_path().is_file():
        return "developer", terrain_bundle.verdict("loaded", None, str(default_path()))
    chosen = terrain_bundle.select()
    if chosen["check"] != "loaded":
        chosen["reason"] = f"{chosen['reason']}; a developer build with npm run build needs Rust"
    return "bundled", chosen


def core():
    if "core" not in STATE:
        source, chosen = locate()
        found, reason = (None, chosen["reason"]) if chosen["check"] != "loaded" else load(chosen["path"], chosen["data"])
        check = "loaded" if found else "mismatched" if chosen["check"] == "mismatched" else "missing"
        STATE.update(core=found, reason=reason, source=source, check=check, expected=chosen["expected"], actual=chosen["actual"])
        if reason:
            print(f"blendworks: {reason}; using the Python reference kernels ({terrain_bundle.SLOWDOWN})", file=sys.stderr, flush=True)
    return STATE["core"]


def require():
    found = core()
    if found is None:
        raise CoreMissing(f"the native core is required here but did not load: {STATE['reason']}")
    return found


def status():
    found = core()
    return {"loaded": found is not None, "path": str(found.path if found else configured_path()), "reason": STATE["reason"], "required": required(), "source": STATE["source"] if found else None, "check": STATE["check"], "platform": terrain_bundle.platform_key()}


def report():
    found = core()
    if found is not None:
        return {"engine": "native", "source": STATE["source"], "check": "loaded", "path": str(found.path)}
    return {"engine": "python", "check": STATE["check"], "reason": STATE["reason"], "slowdown": terrain_bundle.SLOWDOWN}
