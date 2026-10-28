import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bridge", "judge"))

import judge_pass
from judge_common import FileLockError, exit_on_lock, script_arguments, shared_access, split_arguments

positional, options = split_arguments(script_arguments(), {**judge_pass.PASS_DEFAULTS, "outcome": ""})
asset, out_dir = positional[0], os.path.abspath(positional[1])


def allocation_failed(context):
    print("Malloc returns null: len=17179869184 in BLI_array, total 2147483648", file=sys.stderr, flush=True)
    os._exit(11)


def python_memory(context):
    raise MemoryError()


def lock_in_stage(context):
    raise FileLockError("a file stayed locked by another process for more than 2.0 s: \"measurements.json\"")


def lock_while_writing(context):
    exit_on_lock(FileLockError("a file stayed locked by another process for more than 2.0 s: \"progress.log\""))


def held(context):
    def locked():
        raise PermissionError(13, "The process cannot access the file because it is being used by another process", "measurements.json")

    return shared_access(locked)


def not_finite(context):
    return {"measurements": {"value": float("nan")}}


OUTCOMES = {"allocation": allocation_failed, "python-memory": python_memory, "lock": lock_in_stage, "lock-exit": lock_while_writing, "held": held, "nan": not_finite}

judge_pass.STAGES["measure"] = OUTCOMES[options["outcome"]]
judge_pass.run_pass(os.path.abspath(asset), out_dir, options)
