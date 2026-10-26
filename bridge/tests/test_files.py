import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run

OUTSIDE_PATHS = ["../escape.glb", "sub/../../escape.glb", "/tmp/escape.glb"]
if os.name == "nt":
    OUTSIDE_PATHS += ["..\\escape.glb", "C:/escape.glb", "\\\\server\\share\\escape.glb"]


def box(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0, location=[0.0, 0.0, 0.5])


def test_export_writes_each_format(bridge):
    box(bridge)
    for path, file_format in (("out/box.glb", "glb"), ("box.fbx", "fbx"), ("box.obj", "obj")):
        result = bridge.ok("export", path=path)
        assert result["format"] == file_format and result["path"] == path
        assert result["objects"] == ["Box"]
        assert result["bytes"] == os.path.getsize(os.path.join(bridge.workspace, path)) > 0
    with open(os.path.join(bridge.workspace, "out/box.glb"), "rb") as handle:
        assert handle.read(4) == b"glTF"


def test_export_refuses_paths_outside_the_workspace(bridge):
    box(bridge)
    for path in OUTSIDE_PATHS:
        bridge.refuse("export", "forbidden", path=path)
    assert not os.path.exists(os.path.join(os.path.dirname(bridge.workspace), "escape.glb"))


def test_export_refuses_other_formats(bridge):
    box(bridge)
    bridge.refuse("export", "forbidden", path="box.exe")
    bridge.refuse("export", "bad_args", path="box.obj", format="glb")
    bridge.refuse("export", "bad_args", path="box.stl", format="stl")
    bridge.ok("new_scene")
    bridge.refuse("export", "bad_args", path="empty.glb")


def test_save_blend_writes_a_copy(bridge):
    box(bridge)
    result = bridge.ok("save_blend", path="scene.blend")
    assert result["bytes"] > 0 and result["path"] == "scene.blend"
    assert bpy.data.filepath == ""


def test_save_blend_refuses_outside_and_wrong_extension(bridge):
    bridge.refuse("save_blend", "forbidden", path="../scene.blend")
    bridge.refuse("save_blend", "forbidden", path="scene.py")


def test_import_brings_objects_back(bridge):
    box(bridge)
    bridge.ok("export", path="box.glb")
    bridge.ok("export", path="box.obj")
    bridge.ok("export", path="box.fbx")
    for path in ("box.glb", "box.obj", "box.fbx"):
        bridge.ok("new_scene")
        result = bridge.ok("import", path=path)
        assert len(result["objects"]) == 1, (path, result)
        info = bridge.ok("scene_info")
        assert info["totals"]["triangles"] == 12, path
        close(info["bounds"]["min"], [-0.5, -0.5, 0.0])
        close(info["bounds"]["max"], [0.5, 0.5, 1.0])


def test_import_refuses_forbidden_files(bridge):
    for path in OUTSIDE_PATHS:
        bridge.refuse("import", "forbidden", path=path)
    with open(os.path.join(bridge.workspace, "script.py"), "w") as handle:
        handle.write("print('no')\n")
    bridge.refuse("import", "forbidden", path="script.py")
    bridge.refuse("import", "forbidden", path="scene.blend")
    bridge.refuse("import", "not_found", path="missing.glb")


def test_import_refuses_references_outside_the_workspace(bridge):
    document = {"asset": {"version": "2.0"}, "buffers": [{"uri": "../../secret.bin", "byteLength": 4}]}
    with open(os.path.join(bridge.workspace, "evil.gltf"), "w") as handle:
        json.dump(document, handle)
    bridge.refuse("import", "forbidden", path="evil.gltf")
    with open(os.path.join(bridge.workspace, "evil.obj"), "w") as handle:
        handle.write("mtllib ../evil.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    bridge.refuse("import", "forbidden", path="evil.obj")
    with open(os.path.join(bridge.workspace, "inner.mtl"), "w") as handle:
        handle.write("newmtl a\nmap_Kd ../../outside.png\n")
    with open(os.path.join(bridge.workspace, "sly.obj"), "w") as handle:
        handle.write("mtllib inner.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    bridge.refuse("import", "forbidden", path="sly.obj")


run(globals())
