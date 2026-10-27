import os
import shutil
import sys
import tempfile
import traceback

BRIDGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BRIDGE not in sys.path:
    sys.path.insert(0, BRIDGE)

import bpy

from blendworks_bridge import Handler
from blendworks_bridge.commands.scene import reset_scene


class Bridge:
    def __init__(self, workspace, allow_python=False, desktop=False, autosave_seconds=None):
        self.handler = Handler(workspace, allow_python=allow_python, desktop=desktop, autosave_seconds=autosave_seconds)
        self.workspace = self.handler.workspace.root
        self.next_id = 0

    def call(self, cmd, /, **args):
        self.next_id += 1
        reply = self.handler.handle({"id": self.next_id, "cmd": cmd, "args": args})
        assert reply["id"] == self.next_id, reply
        return reply

    def ok(self, cmd, /, **args):
        reply = self.call(cmd, **args)
        assert reply["ok"], f"{cmd} {args} failed: {reply.get('error')}"
        return reply["result"]

    def refuse(self, cmd, expected, /, **args):
        reply = self.call(cmd, **args)
        assert not reply["ok"], f"{cmd} {args} should have been refused with {expected}, got {reply.get('result')}"
        assert reply["error"]["code"] == expected, f"{cmd} {args}: expected {expected}, got {reply['error']}"
        return reply["error"]["message"]

    def info(self, name):
        objects = {entry["name"]: entry for entry in self.ok("scene_info")["objects"]}
        assert name in objects, f"{name} not in {sorted(objects)}"
        return objects[name]


def close(actual, expected, tolerance=1e-4):
    if isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected), (actual, expected)
        for a, e in zip(actual, expected):
            close(a, e, tolerance)
        return
    assert abs(actual - expected) <= tolerance, f"{actual} is not within {tolerance} of {expected}"


def snapshot():
    scene = bpy.context.scene
    objects = []
    for obj in sorted(scene.objects, key=lambda o: o.name):
        entry = [
            obj.name,
            obj.type,
            [round(value, 6) for row in obj.matrix_world for value in row],
            obj.parent.name if obj.parent else None,
            [modifier.name for modifier in obj.modifiers],
            obj.hide_get(),
            obj.hide_render,
            obj.data.name if obj.data else None,
        ]
        if obj.type == "MESH":
            mesh = obj.data
            entry.append([tuple(round(c, 6) for c in vertex.co) for vertex in mesh.vertices])
            entry.append([tuple(polygon.vertices) for polygon in mesh.polygons])
            entry.append([polygon.material_index for polygon in mesh.polygons])
            entry.append([material.name if material else None for material in mesh.materials])
            entry.append([layer.name for layer in mesh.uv_layers])
        objects.append(entry)
    return {
        "objects": objects,
        "meshes": sorted(mesh.name for mesh in bpy.data.meshes),
        "materials": sorted(material.name for material in bpy.data.materials),
        "camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
    }


def run(namespace, **bridge_options):
    tests = [(name, value) for name, value in namespace.items() if name.startswith("test_") and callable(value)]
    failures = []
    for name, test in tests:
        workspace = tempfile.mkdtemp(prefix="blendworks-test-")
        try:
            reset_scene(bpy.context.scene)
            test(Bridge(workspace, **bridge_options))
            print(f"ok   {name}")
        except Exception:
            failures.append(name)
            print(f"FAIL {name}")
            traceback.print_exc(file=sys.stdout)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
    print(f"{len(tests) - len(failures)} of {len(tests)} passed")
    sys.stdout.flush()
    if failures:
        raise AssertionError(f"failed: {', '.join(failures)}")
