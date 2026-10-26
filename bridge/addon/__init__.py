import os
import sys

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

from .blendworks_bridge import Handler
from .server import BridgeServer

DEFAULT_PORT = 9876
TICK_SECONDS = 0.02
STATE = {"server": None, "error": ""}


def launch_options(argv=None):
    argv = sys.argv if argv is None else argv
    own = argv[argv.index("--") + 1 :] if "--" in argv else []
    options = {"allow_python": "--allow-python" in own}
    for flag, key in (("--workspace", "workspace"), ("--port", "port")):
        if flag in own and own.index(flag) + 1 < len(own):
            options[key] = own[own.index(flag) + 1]
    return options


def preferences():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def settings():
    prefs = preferences()
    options = launch_options()
    port = int(options.get("port", prefs.port if prefs else DEFAULT_PORT))
    workspace = options.get("workspace", prefs.workspace if prefs else "") or default_workspace()
    return port, bpy.path.abspath(workspace), options["allow_python"]


def default_workspace():
    return os.path.join(os.path.expanduser("~"), "Blendworks")


def running():
    server = STATE["server"]
    return server is not None and server.running


def start_server():
    if running():
        return STATE["server"]
    port, workspace, allow_python = settings()
    server = BridgeServer(Handler(workspace, allow_python=allow_python, desktop=True), port)
    try:
        server.start()
    except OSError as error:
        STATE["error"] = f"port {port}: {error.strerror or error}"
        raise
    STATE["server"] = server
    STATE["error"] = ""
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=0.0, persistent=True)
    return server


def stop_server():
    server = STATE["server"]
    STATE["server"] = None
    if server is not None:
        server.stop()
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)


def tick():
    server = STATE["server"]
    if server is None or not server.running:
        return None
    server.pump()
    return TICK_SECONDS


def auto_start():
    prefs = preferences()
    if prefs is not None and prefs.auto_start and not running():
        try:
            start_server()
        except OSError:
            pass
    return None


class BlendworksPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    port: IntProperty(name="Port", description="Localhost port of the bridge", default=DEFAULT_PORT, min=1024, max=65535)
    workspace: StringProperty(
        name="Workspace",
        description="Folder that holds every import, export and save",
        subtype="DIR_PATH",
        default=default_workspace(),
    )
    auto_start: BoolProperty(name="Start with Blender", description="Start the bridge when Blender starts", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "port")
        layout.prop(self, "workspace")
        layout.prop(self, "auto_start")
        layout.label(text="run_python is available only when Blender is started with -- --allow-python")


class BLENDWORKS_OT_toggle_server(bpy.types.Operator):
    bl_idname = "blendworks.toggle_server"
    bl_label = "Start or Stop the Blendworks Bridge"
    bl_description = "Start or stop serving bridge commands on 127.0.0.1"

    def execute(self, context):
        if running():
            stop_server()
            self.report({"INFO"}, "Blendworks bridge stopped")
            return {"FINISHED"}
        try:
            server = start_server()
        except OSError:
            self.report({"ERROR"}, f"Blendworks bridge could not start: {STATE['error']}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Blendworks bridge listening on 127.0.0.1:{server.port}")
        return {"FINISHED"}


class BLENDWORKS_PT_panel(bpy.types.Panel):
    bl_label = "Blendworks Bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Blendworks"

    def draw(self, context):
        layout = self.layout
        server = STATE["server"]
        on = running()
        layout.operator(
            BLENDWORKS_OT_toggle_server.bl_idname,
            text="Stop bridge" if on else "Start bridge",
            icon="PAUSE" if on else "PLAY",
            depress=on,
        )
        port, workspace, allow_python = settings()
        column = layout.column(align=True)
        column.label(text=f"Listening on 127.0.0.1:{server.port}" if on else "Stopped")
        column.label(text=f"Workspace: {workspace}")
        if allow_python:
            column.alert = True
            column.label(text="run_python is ON (--allow-python)")
        if STATE["error"]:
            column.alert = True
            column.label(text=STATE["error"])
        prefs = preferences()
        if prefs is not None and not on:
            layout.prop(prefs, "port")


CLASSES = (BlendworksPreferences, BLENDWORKS_OT_toggle_server, BLENDWORKS_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(auto_start, first_interval=0.5)


def unregister():
    stop_server()
    if bpy.app.timers.is_registered(auto_start):
        bpy.app.timers.unregister(auto_start)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
