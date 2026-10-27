import ctypes
import subprocess
import sys
from ctypes import wintypes

LOW_INTEGRITY_SID = "S-1-16-4096"
SE_GROUP_INTEGRITY = 0x20
TOKEN_INTEGRITY_LEVEL = 25
TOKEN_ACCESS = 0x0001 | 0x0002 | 0x0008 | 0x0080
DISABLE_MAX_PRIVILEGE = 0x1
CREATE_SUSPENDED = 0x4
CREATE_UNICODE_ENVIRONMENT = 0x400
STARTF_USESTDHANDLES = 0x100
HANDLE_FLAG_INHERIT = 0x1
INFINITE = 0xFFFFFFFF
EXTENDED_LIMIT_INFORMATION = 9
KILL_ON_JOB_CLOSE = 0x2000
STANDARD_HANDLES = (-10, -11, -12)
LAUNCH_FAILED = 120


class SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class MandatoryLabel(ctypes.Structure):
    _fields_ = [("Label", SidAndAttributes)]


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


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


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimits),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def fail(step):
    print(f"low-integrity launch failed at {step} (error {ctypes.get_last_error()})", file=sys.stderr)
    sys.exit(LAUNCH_FAILED)


def low_integrity_token(advapi32, kernel32):
    process_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_ACCESS, ctypes.byref(process_token)):
        fail("OpenProcessToken")
    restricted = wintypes.HANDLE()
    if not advapi32.CreateRestrictedToken(process_token, DISABLE_MAX_PRIVILEGE, 0, None, 0, None, 0, None, ctypes.byref(restricted)):
        fail("CreateRestrictedToken")
    sid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(LOW_INTEGRITY_SID, ctypes.byref(sid)):
        fail("ConvertStringSidToSidW")
    label = MandatoryLabel(SidAndAttributes(sid, SE_GROUP_INTEGRITY))
    size = ctypes.sizeof(label) + advapi32.GetLengthSid(sid)
    if not advapi32.SetTokenInformation(restricted, TOKEN_INTEGRITY_LEVEL, ctypes.byref(label), size):
        fail("SetTokenInformation")
    return restricted


def kill_on_close_job(kernel32):
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        fail("CreateJobObjectW")
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)):
        fail("SetInformationJobObject")
    return job


def inheritable_standard_handles(kernel32):
    handles = []
    for which in STANDARD_HANDLES:
        handle = kernel32.GetStdHandle(which)
        if handle and handle != wintypes.HANDLE(-1).value:
            kernel32.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
        handles.append(handle)
    return handles


def declare(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = list(arguments)


def libraries():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    handle, dword, pointer, boolean = wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL
    declare(kernel32, "GetCurrentProcess", handle)
    declare(kernel32, "GetStdHandle", handle, dword)
    declare(kernel32, "SetHandleInformation", boolean, handle, dword, dword)
    declare(kernel32, "CreateJobObjectW", handle, pointer, wintypes.LPCWSTR)
    declare(kernel32, "SetInformationJobObject", boolean, handle, ctypes.c_int, pointer, dword)
    declare(kernel32, "AssignProcessToJobObject", boolean, handle, handle)
    declare(kernel32, "TerminateProcess", boolean, handle, ctypes.c_uint)
    declare(kernel32, "ResumeThread", dword, handle)
    declare(kernel32, "WaitForSingleObject", dword, handle, dword)
    declare(kernel32, "GetExitCodeProcess", boolean, handle, ctypes.POINTER(dword))
    declare(advapi32, "OpenProcessToken", boolean, handle, dword, ctypes.POINTER(handle))
    declare(advapi32, "CreateRestrictedToken", boolean, handle, dword, dword, pointer, dword, pointer, dword, pointer, ctypes.POINTER(handle))
    declare(advapi32, "ConvertStringSidToSidW", boolean, wintypes.LPCWSTR, ctypes.POINTER(pointer))
    declare(advapi32, "GetLengthSid", dword, pointer)
    declare(advapi32, "SetTokenInformation", boolean, handle, ctypes.c_int, pointer, dword)
    declare(
        advapi32,
        "CreateProcessAsUserW",
        boolean,
        handle,
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        pointer,
        pointer,
        boolean,
        dword,
        pointer,
        wintypes.LPCWSTR,
        ctypes.POINTER(StartupInfo),
        ctypes.POINTER(ProcessInformation),
    )
    return kernel32, advapi32


def launch(arguments):
    kernel32, advapi32 = libraries()
    token = low_integrity_token(advapi32, kernel32)
    job = kill_on_close_job(kernel32)
    startup = StartupInfo()
    startup.cb = ctypes.sizeof(startup)
    startup.dwFlags = STARTF_USESTDHANDLES
    startup.hStdInput, startup.hStdOutput, startup.hStdError = inheritable_standard_handles(kernel32)
    process = ProcessInformation()
    command = ctypes.create_unicode_buffer(subprocess.list2cmdline(arguments))
    flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
    if not advapi32.CreateProcessAsUserW(token, None, command, None, None, True, flags, None, None, ctypes.byref(startup), ctypes.byref(process)):
        fail("CreateProcessAsUserW")
    if not kernel32.AssignProcessToJobObject(job, process.hProcess):
        kernel32.TerminateProcess(process.hProcess, LAUNCH_FAILED)
        fail("AssignProcessToJobObject")
    kernel32.ResumeThread(process.hThread)
    kernel32.WaitForSingleObject(process.hProcess, INFINITE)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(process.hProcess, ctypes.byref(code))
    return code.value


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "--":
        print("low_integrity.py -- <program> [arguments...]", file=sys.stderr)
        sys.exit(2)
    sys.exit(launch(sys.argv[2:]))
