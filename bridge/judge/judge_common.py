import json
import math
import os
import sys
import time

DEFAULT_MEMORY_MB = 4096
SHARED_ACCESS_SECONDS = 2.0
SHARED_ACCESS_FIRST_PAUSE = 0.01
SHARED_ACCESS_LONGEST_PAUSE = 0.1
DEFAULT_MAX_TRIANGLES = 2_000_000
MEMORY_KINDS = ("address-space", "data")


class JudgeError(Exception):
    def __init__(self, code, message, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}


def script_arguments():
    argv = sys.argv
    return argv[argv.index("--") + 1 :] if "--" in argv else []


def split_arguments(arguments, flags):
    positional = []
    options = dict(flags)
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item.startswith("--") and item[2:] in flags:
            if index + 1 >= len(arguments):
                raise JudgeError("usage", f"{item} needs a value")
            options[item[2:]] = arguments[index + 1]
            index += 2
            continue
        positional.append(item)
        index += 1
    return positional, options


def positive_int(text, name):
    try:
        value = int(text)
    except (TypeError, ValueError):
        raise JudgeError("usage", f"--{name} must be a whole number") from None
    if value <= 0:
        raise JudgeError("usage", f"--{name} must be positive")
    return value


def shared_access(action):
    if os.name != "nt":
        return action()
    deadline = time.monotonic() + SHARED_ACCESS_SECONDS
    pause = SHARED_ACCESS_FIRST_PAUSE
    while True:
        try:
            return action()
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
        time.sleep(pause)
        pause = min(pause * 2, SHARED_ACCESS_LONGEST_PAUSE)


def write_bytes(path, data):
    temporary = path + ".partial"

    def write():
        with open(temporary, "wb") as handle:
            handle.write(data)

    shared_access(write)
    shared_access(lambda: os.replace(temporary, path))


def read_bytes(path):
    def read():
        with open(path, "rb") as handle:
            return handle.read()

    return shared_access(read)


def json_bytes(payload):
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def write_json(path, payload):
    data = json_bytes(payload)
    write_bytes(path, data)
    return data


def is_inside(path, directory):
    real_path = os.path.normcase(os.path.realpath(path))
    real_directory = os.path.normcase(os.path.realpath(directory))
    try:
        return os.path.commonpath([real_path, real_directory]) == real_directory
    except ValueError:
        return False


def memory_kind(text):
    if text not in MEMORY_KINDS:
        raise JudgeError("usage", f"--memory-kind must be one of {', '.join(MEMORY_KINDS)}")
    return text


def apply_memory_cap(memory_bytes, kind="address-space"):
    if sys.platform == "win32":
        return windows_job_cap(memory_bytes)
    return posix_cap(memory_bytes, memory_kind(kind))


def posix_cap(memory_bytes, kind):
    import resource

    which = resource.RLIMIT_DATA if kind == "data" else resource.RLIMIT_AS
    soft, hard = resource.getrlimit(which)
    limit = memory_bytes if hard == resource.RLIM_INFINITY else min(memory_bytes, hard)
    resource.setrlimit(which, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return {"memoryBytes": limit, "memoryKind": kind, "childProcesses": "allowed"}


def cap_address_space(memory_bytes):
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = memory_bytes if hard == resource.RLIM_INFINITY else min(memory_bytes, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
    return {"memoryBytes": limit, "memoryKind": "address-space", "childProcesses": "allowed"}


def lift_address_space():
    import resource

    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (hard, hard))


def windows_job_cap(memory_bytes):
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("reads", "writes", "others", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    limit_active_process = 0x8
    limit_process_memory = 0x100
    limit_die_on_unhandled_exception = 0x400
    limit_kill_on_job_close = 0x2000
    extended_limit_information = 9
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise JudgeError("sandbox", f"could not create a job object (error {ctypes.get_last_error()})")
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = (
        limit_active_process | limit_process_memory | limit_die_on_unhandled_exception | limit_kill_on_job_close
    )
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = memory_bytes
    if not kernel32.SetInformationJobObject(wintypes.HANDLE(job), extended_limit_information, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise JudgeError("sandbox", f"could not set the job limits (error {ctypes.get_last_error()})")
    if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(kernel32.GetCurrentProcess())):
        raise JudgeError("sandbox", f"could not enter the job object (error {ctypes.get_last_error()})")
    return {"memoryBytes": memory_bytes, "memoryKind": "job object", "childProcesses": "blocked"}


def memory_cap_from(options):
    return apply_memory_cap(positive_int(options["memory-mb"], "memory-mb") * 1024 * 1024, options["memory-kind"])


def run_guarded(out_path, work):
    try:
        payload = {"ok": True, **work()}
    except JudgeError as error:
        payload = {**error.extra, "ok": False, "error": {"code": error.code, "message": error.message}}
    except MemoryError:
        payload = {"ok": False, "error": {"code": "memory_cap", "message": "the asset needs more memory than the cap allows"}}
    write_json(out_path, payload)


def rounded(values):
    return [round(value, 6) + 0.0 for value in values]


def distance(first, second):
    return math.sqrt(sum((first[axis] - second[axis]) ** 2 for axis in range(3)))


def stopwatch():
    started = time.perf_counter()
    return lambda: round(time.perf_counter() - started, 3)
