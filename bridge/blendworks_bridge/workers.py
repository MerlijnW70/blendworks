"""Child Blender sessions that run bridge commands in parallel.

The parent writes a job (a list of tasks, each a list of commands) to a folder and starts worker sessions: headless
Blender with the bridge and no autosave. Each worker claims tasks in order by creating a claim file, runs the task's
commands through its own handler, writes the objects the task made to task_<i>.blend with their dependencies, and
then task_<i>.json with the results, the collections and the view-layer state of every object. The parent merges the
tasks in order as they finish; a task whose worker failed, died or was never started is run in the parent instead."""
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time

from .limit_base import MEMORY, TIME, limit

WORKER_MEMORY_BYTES = 2_000_000_000
POLL_SECONDS = 0.05
MAX_WORKERS = limit("batch_workers", 16, "processes", MEMORY,
                    "Child Blender sessions of one batch; each holds a whole Blender in memory, and more than 16 gain little "
                    "when the parent merges their results one after another.")
CLAIM = "claim_{}"
TASK_BLEND = "task_{}.blend"
TASK_JSON = "task_{}.json"
JOB = "job.json"
READY = "ready_{}.json"
SEED = "seed.blend"
MAX_BATCH_TASKS = limit("batch_trees", 200, "trees", TIME,
                        "Trees in one grow_trees call; at 10 to 15 s per tree on one core, 200 trees keep a batch under an hour on a few workers.")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def cgroup_cpus(text=None):
    text = read_text("/sys/fs/cgroup/cpu.max") if text is None else text
    parts = (text or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit() or int(parts[1]) == 0:
        return None
    return max(1, math.floor(int(parts[0]) / int(parts[1])))


def available_cpus():
    if hasattr(os, "process_cpu_count"):
        count = os.process_cpu_count()
    elif hasattr(os, "sched_getaffinity"):
        count = len(os.sched_getaffinity(0))
    else:
        count = os.cpu_count()
    quota = cgroup_cpus()
    count = count or 1
    return min(count, quota) if quota is not None else count


def meminfo_available(text=None):
    text = read_text("/proc/meminfo") if text is None else text
    for line in (text or "").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return None


def cgroup_memory_free(limit_text=None, current_text=None):
    limit_text = read_text("/sys/fs/cgroup/memory.max") if limit_text is None else limit_text
    current_text = read_text("/sys/fs/cgroup/memory.current") if current_text is None else current_text
    limit, current = (limit_text or "").strip(), (current_text or "").strip()
    if not limit.isdigit() or not current.isdigit():
        return None
    return max(0, int(limit) - int(current))


def windows_memory_available():
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong), ("available_extended", ctypes.c_ulonglong)]

    status = Status()
    status.length = ctypes.sizeof(Status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.available_physical)


def available_memory():
    if sys.platform == "win32":
        return windows_memory_available()
    found = [value for value in (meminfo_available(), cgroup_memory_free()) if value is not None]
    return min(found) if found else None


PROBE = "probe"


def plan(tasks, requested=None, cpus=None, memory=PROBE, per_worker=WORKER_MEMORY_BYTES, probe=available_memory):
    """Workers for a job: one per task at most, no more than the CPUs, and no more than the memory available holds at
    per_worker bytes each. memory is the bytes available; PROBE (the default) asks probe() for the host's available
    memory now, and None means unknown, which does not limit. requested caps the count; without it, a job that would
    get fewer than two workers runs serially (0 workers)."""
    cpus = available_cpus() if cpus is None else cpus
    memory = probe() if memory == PROBE else memory
    limits = {"tasks": tasks, "cpus": cpus, "most": MAX_WORKERS}
    if memory is not None:
        limits["memory"] = int(memory // per_worker)
    if requested is not None:
        limits["requested"] = requested
    workers = max(0, min(limits.values()))
    reason = min(limits, key=lambda key: limits[key])
    if workers < 2 and requested is None:
        workers = 0
    return {"workers": workers, "threads": max(1, cpus // max(1, workers)), "cpus": cpus,
            "memory_available": memory, "worker_memory_estimate": per_worker, "limited_by": reason}


class Pool:
    def __init__(self, tasks, workspace, threads, seed_ids=()):
        self.folder = tempfile.mkdtemp(prefix="blendworks-workers-")
        self.tasks = tasks
        self.threads = threads
        self.processes = []
        self.started = []
        self.seed = None
        if seed_ids:
            import bpy

            self.seed = os.path.join(self.folder, SEED)
            bpy.data.libraries.write(self.seed, set(seed_ids), fake_user=True, compress=False)
        with open(os.path.join(self.folder, JOB), "w", encoding="utf-8") as handle:
            json.dump({"tasks": tasks, "workspace": workspace, "seed": self.seed}, handle)

    def start(self, count):
        import bpy

        package = __name__.rpartition(".")[0]
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        boot = f"import sys; sys.path.insert(0, {root!r}); import importlib; importlib.import_module({package + '.workers'!r}).child_main()"
        for index in range(count):
            log = open(os.path.join(self.folder, f"worker_{index}.log"), "wb")
            command = [bpy.app.binary_path, "--background", "--factory-startup", "--threads", str(self.threads), "--python-expr", boot, "--", self.folder, str(index)]
            self.started.append(time.time())
            self.processes.append(subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
            log.close()

    def startup_seconds(self):
        found = []
        for index, started in enumerate(self.started):
            record = read_json(os.path.join(self.folder, READY.format(index)))
            if record is not None:
                found.append(round(record["ready"] - started, 3))
        return found

    def finished(self, index):
        return read_json(os.path.join(self.folder, TASK_JSON.format(index)))

    def claimant(self, index):
        text = read_text(os.path.join(self.folder, CLAIM.format(index)))
        return int(text) if text and text.strip().isdigit() else None

    def alive(self, worker):
        return 0 <= worker < len(self.processes) and self.processes[worker].poll() is None

    def wait(self, index):
        """Wait for task index; return its record, or None when no worker can still deliver it."""
        while True:
            record = self.finished(index)
            if record is not None:
                return record
            worker = self.claimant(index)
            if worker is not None and not self.alive(worker) and self.finished(index) is None:
                return None
            if worker is None and not any(process.poll() is None for process in self.processes):
                return None
            time.sleep(POLL_SECONDS)

    def blend(self, index):
        return os.path.join(self.folder, TASK_BLEND.format(index))

    def stop(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
        for process in self.processes:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
            if process.stdin is not None:
                process.stdin.close()
        remove_tree(self.folder)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False


def remove_tree(folder):
    import shutil

    shutil.rmtree(folder, ignore_errors=True)


def read_json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def write_json(path, value):
    partial = f"{path}.partial"
    with open(partial, "w", encoding="utf-8") as handle:
        json.dump(value, handle)
    os.replace(partial, path)


def claim(folder, index, worker):
    try:
        handle = os.open(os.path.join(folder, CLAIM.format(index)), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(handle, str(worker).encode("ascii"))
    os.close(handle)
    return True


def exit_with_parent():
    def watch():
        try:
            while sys.stdin.buffer.read(4096):
                pass
        except (OSError, ValueError, AttributeError):
            pass
        os._exit(3)

    threading.Thread(target=watch, daemon=True).start()


def run_steps(handler, txn, steps):
    """Run commands in order in this session as the handler runs them, inside the caller's transaction."""
    from .handler import Context
    from .schema import validate

    results = []
    for name, args in steps:
        command = handler.registry.get(name)
        results.append(command.run(Context(handler, txn), validate(command.schema, args)))
    return results


def peak_memory():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD), ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                        ("peak_paged_pool", ctypes.c_size_t), ("paged_pool", ctypes.c_size_t), ("peak_nonpaged_pool", ctypes.c_size_t),
                        ("nonpaged_pool", ctypes.c_size_t), ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        if not query(current(), ctypes.byref(counters), counters.cb):
            return None
        return int(counters.peak_working_set)
    import resource

    scale = 1 if sys.platform == "darwin" else 1024
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale)


def child_main():
    import bpy

    from . import blendfile
    from .handler import Handler
    from .transaction import NoSnapshot

    folder, worker = sys.argv[sys.argv.index("--") + 1:][:2]
    worker = int(worker)
    exit_with_parent()
    job = read_json(os.path.join(folder, JOB))
    handler = Handler(job["workspace"], allow_python=False, autosave_seconds=None)
    handler.handle({"cmd": "new_scene", "args": {}})
    if job["seed"]:
        blendfile.load_seed(job["seed"], bpy.context.scene)
    write_json(os.path.join(folder, READY.format(worker)), {"ready": time.time()})
    for index, task in enumerate(job["tasks"]):
        if not claim(folder, index, worker):
            continue
        started = time.perf_counter()
        before = {obj.name for obj in bpy.data.objects}
        try:
            results = run_steps(handler, NoSnapshot(), task)
        except Exception as error:
            write_json(os.path.join(folder, TASK_JSON.format(index)), {"error": {"type": type(error).__name__, "message": str(error)}})
            sys.stdout.flush()
            os._exit(0)
        made = [obj for obj in bpy.data.objects if obj.name not in before]
        built = time.perf_counter() - started
        blendfile.write_objects(os.path.join(folder, TASK_BLEND.format(index)), made)
        record = {"results": results, **blendfile.object_state(made, bpy.context.view_layer), "worker": worker,
                  "seconds": {"build": round(built, 3), "write": round(time.perf_counter() - started - built, 3)}, "peak_memory": peak_memory()}
        write_json(os.path.join(folder, TASK_JSON.format(index)), record)
        blendfile.remove_objects(made)
    sys.stdout.flush()
    os._exit(0)
