import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import BRIDGE, run

sys.path.insert(0, BRIDGE)
import build_addon

MODULE = "bl_ext.user_default.blendworks"
CHILD = """
import bpy, json, os, sys, threading, time
zip_path, port, workspace, done_flag, result_path = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.extensions.package_install_files(filepath=zip_path, repo="user_default", enable_on_install=True)
module = sys.modules["MODULE"]
prefs = bpy.context.preferences.addons["MODULE"].preferences
prefs.port = int(port)
prefs.workspace = workspace
started = bpy.ops.blendworks.toggle_server()
server = module.STATE["server"]
threads = set()
original = server.handler.handle_line
def tracked(line):
    threads.add(threading.get_ident())
    return original(line)
server.handler.handle_line = tracked
timer = bpy.app.timers.is_registered(module.tick)
deadline = time.monotonic() + 180
while not os.path.exists(done_flag) and time.monotonic() < deadline:
    module.tick()
    time.sleep(0.005)
stopped = bpy.ops.blendworks.toggle_server()
with open(result_path, "w") as handle:
    json.dump({
        "started": sorted(started), "stopped": sorted(stopped), "timer": timer,
        "timer_after_stop": bpy.app.timers.is_registered(module.tick), "running_after_stop": module.running(),
        "threads": len(threads), "only_main_thread": threads == {threading.get_ident()},
        "desktop": server.handler.desktop, "python": server.handler.allow_python,
    }, handle)
""".replace("MODULE", MODULE)


def free_port():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def connect(port, child, timeout=120.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise AssertionError(f"the add-on Blender exited early: {child.stderr.read()[-3000:]}")
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=60)
        except OSError:
            time.sleep(0.2)
    raise AssertionError("the add-on never listened")


class Client:
    def __init__(self, connection):
        self.connection = connection
        self.reader = connection.makefile("rb")
        self.next_id = 0

    def send(self, cmd, **args):
        self.next_id += 1
        request = {"id": self.next_id, "cmd": cmd, "args": args}
        self.connection.sendall(json.dumps(request).encode("utf-8") + b"\n")
        reply = json.loads(self.reader.readline())
        assert reply["id"] == self.next_id, reply
        return reply


def test_build_contains_the_add_on_and_the_shared_handler(bridge):
    output = build_addon.build(os.path.join(tempfile.mkdtemp(prefix="blendworks-addon-"), "addon.zip"))
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        manifest = archive.read("blender_manifest.toml").decode("utf-8")
    for required in ("__init__.py", "server.py", "blendworks_bridge/handler.py", "blendworks_bridge/commands/render.py"):
        assert required in names, required
    assert not any("__pycache__" in name or name.startswith("tests/") for name in names)
    assert 'id = "blendworks"' in manifest and 'type = "add-on"' in manifest


def test_installed_add_on_serves_the_handler_over_its_socket(bridge):
    folder = tempfile.mkdtemp(prefix="blendworks-addon-")
    archive = build_addon.build(os.path.join(folder, "blendworks-addon.zip"))
    workspace = os.path.join(folder, "workspace")
    done_flag = os.path.join(folder, "done")
    result_path = os.path.join(folder, "result.json")
    port = free_port()
    environment = dict(os.environ, BLENDER_USER_RESOURCES=os.path.join(folder, "user"))
    child = subprocess.Popen(
        [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1", "--python-expr", CHILD,
         "--", archive, str(port), workspace, done_flag, result_path],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        client = Client(connect(port, child))
        described = client.send("describe")["result"]
        assert described["transport"] == "desktop" and described["python"] is False
        assert "run_python" not in [entry["name"] for entry in described["commands"]]
        assert client.send("new_scene")["result"]["removed_objects"] == 3
        assert client.send("add_primitive", type="cube", name="Box", size=1.0)["ok"]
        info = client.send("scene_info")["result"]
        assert [entry["name"] for entry in info["objects"]] == ["Box"]
        assert client.send("boolean", name="Box", cutter="Ghost")["error"]["code"] == "not_found"
        assert client.send("export", path="../escape.glb")["error"]["code"] == "forbidden"
        assert client.send("run_python", code="result = 1")["error"]["code"] == "forbidden"
        preview = client.send("render_preview", engine="cycles", resolution=64, samples=2)["result"]
        assert base64.b64decode(preview["images"][0]["data"])[:8] == b"\x89PNG\r\n\x1a\n"
        exported = client.send("export", path="box.glb")["result"]
        assert os.path.getsize(os.path.join(workspace, "box.glb")) == exported["bytes"]
        client.connection.sendall(b'{"id": 99, "cmd": "quit"}\n')
        assert json.loads(client.reader.readline()) == {"id": 99, "ok": True, "result": {"quit": True}}
        assert client.reader.readline() == b""
        second = Client(connect(port, child))
        assert second.send("scene_info")["result"]["totals"]["objects"] == 1
        second.connection.close()
    finally:
        with open(done_flag, "w") as handle:
            handle.write("done")
        try:
            child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            child.kill()
    assert child.returncode == 0, child.stderr.read()[-3000:]
    with open(result_path) as handle:
        result = json.load(handle)
    assert result["started"] == ["FINISHED"] and result["stopped"] == ["FINISHED"]
    assert result["timer"] is True and result["timer_after_stop"] is False and result["running_after_stop"] is False
    assert result["threads"] == 1 and result["only_main_thread"] is True
    assert result["desktop"] is True and result["python"] is False


run(globals())
