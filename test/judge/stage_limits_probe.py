import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bridge", "judge"))

import resource

import judge_pass
import judge_render_stages
from judge_common import script_arguments, split_arguments

positional, options = split_arguments(script_arguments(), judge_pass.PASS_DEFAULTS)
asset, out_dir = positional[0], os.path.abspath(positional[1])
seen = {}


def limits():
    return {"addressSpace": list(resource.getrlimit(resource.RLIMIT_AS)), "data": list(resource.getrlimit(resource.RLIMIT_DATA)), "unlimited": resource.RLIM_INFINITY}


measure = judge_pass.STAGES["measure"]
probe = judge_render_stages.resolve_backend


def measuring(context):
    seen["measure"] = limits()
    return measure(context)


def probing(backend, order):
    seen["probe"] = limits()
    return probe(backend, order)


judge_pass.STAGES["measure"] = measuring
judge_render_stages.resolve_backend = probing
judge_pass.run_pass(os.path.abspath(asset), out_dir, options)
with open(os.path.join(out_dir, "limits.json"), "w", encoding="utf-8") as handle:
    json.dump(seen, handle)
