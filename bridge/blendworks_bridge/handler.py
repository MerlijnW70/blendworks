import json

import bpy

from . import commands
from .errors import BridgeError, bad_args, forbidden
from .operators import operator_context
from .registry import COMMANDS, Registry
from .schema import validate
from .transaction import Transaction
from .workspace import Workspace

PYTHON_COMMAND = "run_python"


class Context:
    def __init__(self, handler, txn):
        self.handler = handler
        self.registry = handler.registry
        self.workspace = handler.workspace
        self.desktop = handler.desktop
        self.allow_python = handler.allow_python
        self.txn = txn
        self.scene = bpy.context.scene
        self.view_layer = bpy.context.view_layer
        self.view_layer.update()

    def depsgraph(self):
        self.view_layer.update()
        return bpy.context.evaluated_depsgraph_get()


class Handler:
    def __init__(self, workspace, allow_python=False, desktop=False):
        commands.load()
        self.workspace = workspace if isinstance(workspace, Workspace) else Workspace(workspace)
        self.allow_python = bool(allow_python)
        self.desktop = bool(desktop)
        available = {name: cmd for name, cmd in COMMANDS.items() if self.allow_python or name != PYTHON_COMMAND}
        self.registry = Registry(available)

    def handle_line(self, line):
        if isinstance(line, bytes):
            try:
                line = line.decode("utf-8")
            except UnicodeDecodeError:
                return encode(error_reply(None, bad_args("the request is not UTF-8")))
        try:
            request = json.loads(line)
        except ValueError as error:
            return encode(error_reply(None, bad_args(f"the request is not JSON: {error}")))
        return encode(self.handle(request))

    def handle(self, request):
        request_id = request.get("id") if isinstance(request, dict) else None
        if not valid_id(request_id):
            request_id = None
        try:
            name, args = parse_request(request)
            return {"id": request_id, "ok": True, "result": self.run(name, args)}
        except BridgeError as error:
            return error_reply(request_id, error)

    def run(self, name, args):
        command = self.registry.get(name)
        if command is None:
            if name == PYTHON_COMMAND:
                raise forbidden("run_python is off; start the bridge with --allow-python to enable it")
            raise bad_args(f"unknown command {name}; call describe for the list")
        cleaned = validate(command.schema, args)
        if command.mutates and self.desktop:
            ensure_object_mode()
        txn = Transaction(bpy.context.scene, bpy.context.view_layer)
        try:
            result = command.run(Context(self, txn), cleaned)
            json.dumps(result, allow_nan=False)
        except BridgeError:
            txn.rollback()
            raise
        except Exception as error:
            txn.rollback()
            raise BridgeError("failed", f"{name} failed: {type(error).__name__}: {error}") from error
        if command.mutates:
            txn.commit()
            if self.desktop:
                push_undo(name)
        else:
            txn.rollback()
        return result


def parse_request(request):
    if not isinstance(request, dict):
        raise bad_args("the request must be a JSON object")
    unknown = sorted(str(key) for key in request if key not in ("id", "cmd", "args"))
    if unknown:
        raise bad_args(f"the request has unknown field(s): {', '.join(unknown)}")
    if "id" in request and not valid_id(request["id"]):
        raise bad_args("id must be a number or a string")
    name = request.get("cmd")
    if not isinstance(name, str) or not name:
        raise bad_args("cmd must be a command name")
    args = request.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise bad_args("args must be an object")
    return name, args


def valid_id(value):
    if isinstance(value, bool):
        return False
    return value is None or isinstance(value, (int, str)) or (isinstance(value, float) and value.is_integer())


def error_reply(request_id, error):
    return {"id": request_id, "ok": False, "error": {"code": error.code, "message": error.message}}


def encode(reply):
    try:
        return json.dumps(reply, allow_nan=False, separators=(",", ":"))
    except ValueError as error:
        fallback = BridgeError("failed", f"the result could not be encoded: {error}")
        return json.dumps(error_reply(reply.get("id"), fallback), separators=(",", ":"))


def ensure_object_mode():
    obj = bpy.context.view_layer.objects.active
    if obj is None or obj.mode == "OBJECT":
        return
    with bpy.context.temp_override(**operator_context(obj)):
        bpy.ops.object.mode_set(mode="OBJECT")


def push_undo(name):
    try:
        if bpy.ops.ed.undo_push.poll():
            bpy.ops.ed.undo_push(message=f"Blendworks: {name}")
    except RuntimeError:
        pass
