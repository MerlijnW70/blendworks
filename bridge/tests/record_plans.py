"""Records the calls an example script makes, for test_example_plans.py.

Run: blender -b --factory-startup --python bridge/tests/record_plans.py -- <example.py> <out dir> <plans.json>
It runs the example with tiny renders, records every call with whether it succeeded, and merges the list into
plans.json under the example's file name. Arguments are stored as sent, so validate sees exactly what ran."""
import copy
import json
import os
import runpy
import sys

ARGS = sys.argv[sys.argv.index("--") + 1:]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from blendworks_bridge import Handler

EXAMPLE, OUT, PLANS = ARGS[0], ARGS[1], ARGS[2]
SKIPPED = ("validate", "describe")
original = Handler.handle
recorded = []


def tiny(name, args):
    if name == "render_final":
        args.update(width=32, height=32, samples=1)
        args.pop("time_limit", None)
    elif name == "render_preview":
        args.update(resolution=64, samples=1)


def handle(self, request):
    name = request.get("cmd") if isinstance(request, dict) else None
    if name in SKIPPED or not isinstance(request, dict):
        return original(self, request)
    sent = copy.deepcopy(request.get("args") or {})
    tiny(name, request.setdefault("args", {}))
    reply = original(self, request)
    recorded.append({"cmd": name, "args": sent, "ok": bool(reply.get("ok"))})
    return reply


Handler.handle = handle
sys.argv = [EXAMPLE, "--", OUT]
try:
    runpy.run_path(EXAMPLE, run_name="__main__")
except SystemExit:
    pass
plans = {}
if os.path.exists(PLANS):
    with open(PLANS, encoding="utf-8") as handle_file:
        plans = json.load(handle_file)
plans[os.path.basename(EXAMPLE)] = recorded
with open(PLANS, "w", encoding="utf-8", newline="\n") as handle_file:
    json.dump(plans, handle_file, separators=(",", ":"), sort_keys=True)
print(f"recorded {len(recorded)} calls of {EXAMPLE}")
