import json
import os
import sys

DEFAULT_MEMORY_MB = 4096
DEFAULT_MAX_TRIANGLES = 2_000_000


class JudgeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


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


def write_json(path, payload):
    temporary = path + ".partial"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(temporary, path)


def is_inside(path, directory):
    real_path = os.path.normcase(os.path.realpath(path))
    real_directory = os.path.normcase(os.path.realpath(directory))
    try:
        return os.path.commonpath([real_path, real_directory]) == real_directory
    except ValueError:
        return False


def apply_memory_cap(memory_bytes):
    if sys.platform == "win32":
        return windows_job_cap(memory_bytes)
    return posix_cap(memory_bytes)


def posix_cap(memory_bytes):
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limit = memory_bytes if hard == resource.RLIM_INFINITY else min(memory_bytes, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return {"memoryBytes": limit, "childProcesses": "allowed"}


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
    return {"memoryBytes": memory_bytes, "childProcesses": "blocked"}


def run_guarded(out_path, work):
    try:
        payload = {"ok": True, **work()}
    except JudgeError as error:
        payload = {"ok": False, "error": {"code": error.code, "message": error.message}}
    except MemoryError:
        payload = {"ok": False, "error": {"code": "memory_cap", "message": "the asset needs more memory than the cap allows"}}
    write_json(out_path, payload)
