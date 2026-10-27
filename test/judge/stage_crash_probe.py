import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bridge", "judge"))

import judge_pass
from judge_common import script_arguments, split_arguments

positional, options = split_arguments(script_arguments(), {**judge_pass.PASS_DEFAULTS, "crash-stage": "", "crash-kind": "exit"})
asset, out_dir = positional[0], os.path.abspath(positional[1])
original = judge_pass.STAGES[options["crash-stage"]]


def failing(context):
    if options["crash-kind"] == "hang":
        time.sleep(600)
    os._exit(3)


judge_pass.STAGES[options["crash-stage"]] = failing
judge_pass.run_pass(os.path.abspath(asset), out_dir, options)
