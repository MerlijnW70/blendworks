"""Request handler: validates a request, runs a command in a context and encodes the reply."""

import json
import os
import time

import bpy

from . import commands
from . import floating_origin
from .autosave import FOLDER, Autosave, interval_from_environment, journaled
from .errors import BridgeError, bad_args, failed, forbidden
from .journal import ReadRecorder, RecordingWorkspace
from .operators import operator_context
from .plan import without_timeout
from .policy import UNDO
from .registry import COMMANDS, Registry
from .schema import validate
from .transaction import NoSnapshot, Transaction
from .workspace import Workspace

PYTHON_COMMAND = "run_python"
FROM_ENVIRONMENT = "environment"


class Context:
    def __init__(self, handler, txn, workspace=None):
        self.handler = handler
        self.registry = handler.registry
        self.workspace = workspace or handler.workspace
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
    def __init__(self, workspace, allow_python=False, desktop=False, autosave_seconds=FROM_ENVIRONMENT):
        commands.load()
        self.workspace = workspace if isinstance(workspace, Workspace) else Workspace(workspace)
        self.allow_python = bool(allow_python)
        self.desktop = bool(desktop)
        available = {name: cmd for name, cmd in COMMANDS.items() if self.allow_python or name != PYTHON_COMMAND}
        self.registry = Registry(available)
        if self.desktop:
            autosave_seconds = None
        elif autosave_seconds == FROM_ENVIRONMENT:
            autosave_seconds = interval_from_environment()
        self.autosave = Autosave(self.workspace, autosave_seconds, self.replay)
        self.snapshots = 0

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
        self.autosave.touch()
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
        cleaned = self.cleaned(command, args)
        if command.mutates and self.desktop:
            ensure_object_mode()
        self.autosave.before(command)
        recorder = ReadRecorder(self.workspace.root, os.path.join(self.workspace.root, FOLDER))
        watched = self.autosave.enabled and journaled(command)
        started = time.perf_counter()
        if watched:
            with recorder:
                result = self.execute(command, cleaned, RecordingWorkspace(self.workspace, recorder))
        else:
            result = self.execute(command, cleaned)
        seconds = time.perf_counter() - started
        self.autosave.after(command, args, recorder.paths, seconds)
        return result

    def execute(self, command, cleaned, workspace=None):
        txn = self.transaction(command)
        try:
            context = Context(self, txn, workspace)
            floating_origin.begin()
            result = command.run(context, cleaned)
            if command.policy.renders and isinstance(result, dict) and floating_origin.report():
                result["camera_relative"] = floating_origin.report()
            json.dumps(result, allow_nan=False)
        except BridgeError:
            txn.rollback()
            raise
        except Exception as error:
            txn.rollback()
            raise BridgeError("failed", f"{command.name} failed: {type(error).__name__}: {error}") from error
        txn.commit()
        return result

    def cleaned(self, command, args):
        cleaned = validate(command.schema, without_timeout(command, args))
        broken = command.rules(cleaned) if command.rules is not None else []
        if broken:
            raise bad_args("; ".join(problem["message"] for problem in broken))
        return cleaned

    def replay(self, name, args):
        command = self.registry.get(name)
        if command is None:
            raise failed(f"{name} is not a command of this session")
        return self.execute(command, self.cleaned(command, args))

    def idle_wait(self):
        return self.autosave.idle_wait()

    def idle(self):
        return self.autosave.idle()

    def transaction(self, command):
        if command.snapshot != UNDO:
            return NoSnapshot()
        txn = Transaction(command.name, self.desktop).begin()
        self.snapshots += 1
        return txn


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
