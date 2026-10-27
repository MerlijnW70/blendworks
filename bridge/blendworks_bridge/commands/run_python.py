import contextlib
import io
import json
import traceback

import bmesh
import bpy
import mathutils

from .. import limits
from ..errors import failed
from ..registry import command
from ..schema import string


@command(
    "run_python",
    "DANGEROUS: run arbitrary Python inside Blender; set result to return a JSON value. Off unless --allow-python.",
    {"code": string("Python source to run with bpy, bmesh and mathutils in scope.", max_length=limits.MAX_PYTHON_SOURCE)},
    ["code"],
    dangerous=True,
    slow=True,
    destructive=True,
)
def run_python(ctx, args):
    namespace = {"bpy": bpy, "bmesh": bmesh, "mathutils": mathutils, "result": None, "__name__": "blendworks_run_python"}
    output = io.StringIO()
    ctx.txn.guard_image_pixels()
    try:
        compiled = compile(args["code"], "<run_python>", "exec")
        with contextlib.redirect_stdout(output):
            exec(compiled, namespace)
    except (Exception, SystemExit) as error:
        lines = traceback.format_exception_only(type(error), error)
        raise failed(f"the code raised {''.join(lines).strip()}; stdout: {output.getvalue()[-2000:]}") from error
    return {"stdout": output.getvalue()[-100_000:], "result": json_value(namespace.get("result"))}


def json_value(value):
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)
