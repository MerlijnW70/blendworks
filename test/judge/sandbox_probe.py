import errno
import json
import os
import socket
import subprocess
import sys
import time

arguments = sys.argv[sys.argv.index("--") + 1 :]
bridge_dir, mode, out_path = arguments[0], arguments[1], arguments[2]
memory_mb = int(arguments[arguments.index("--memory-mb") + 1])
sys.path.insert(0, bridge_dir)

from judge_common import apply_memory_cap

result = {"limits": apply_memory_cap(memory_mb * 1024 * 1024)}

if mode == "sleep":
    time.sleep(600)

try:
    held = bytearray(memory_mb * 2 * 1024 * 1024)
    result["memory"] = f"allocated {len(held)} bytes"
    del held
except MemoryError:
    result["memory"] = "refused"

try:
    connection = socket.create_connection(("1.1.1.1", 53), timeout=5)
    connection.close()
    result["network"] = "connected"
except OSError as error:
    result["network"] = "unreachable" if error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH) else f"error {error.errno}"

try:
    subprocess.run([sys.executable, "-c", "pass"], check=True, timeout=30)
    result["childProcess"] = "started"
except (OSError, subprocess.SubprocessError):
    result["childProcess"] = "blocked"

result["environment"] = sorted(name for name in os.environ if name.startswith("BLENDER_USER"))
result["gpus"] = [os.environ.get("CUDA_VISIBLE_DEVICES"), os.environ.get("HIP_VISIBLE_DEVICES")]

with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(result, handle)
