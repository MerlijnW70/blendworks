import json
import os
import sys

arguments = sys.argv[sys.argv.index("--") + 1 :]
out_path = arguments[0]
reads = arguments[1 : arguments.index("--writes")]
writes = arguments[arguments.index("--writes") + 1 : arguments.index("--memory-mb")]
result = {"read": {}, "write": {}}

for path in reads:
    try:
        with open(path, "rb") as handle:
            handle.read(16)
        result["read"][path] = "read"
    except OSError as error:
        result["read"][path] = f"refused {error.errno}"

for path in writes:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("probe")
        result["write"][path] = "written"
    except OSError as error:
        result["write"][path] = f"refused {error.errno}"

result["processes"] = sorted(name for name in os.listdir("/proc") if name.isdigit()) if os.path.isdir("/proc") else []

with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(result, handle)
