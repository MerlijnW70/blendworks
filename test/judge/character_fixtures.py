FIXTURE_DEPS = ("bridge/blendworks_bridge", "docs/examples/character_models.py")
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "docs", "examples"))

import character_models
from blendworks_bridge import Handler

HANDLER = None


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def cmd(name, /, **args):
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    return reply["result"]


def unweight_one_vertex():
    body = bpy.data.objects["HeroBody"]
    vertex = max(body.data.vertices, key=lambda item: item.co.z)
    for group in body.vertex_groups:
        group.remove([vertex.index])


def fifth_influence():
    legs = bpy.data.objects["HeroLegs"]
    vertex = legs.data.vertices[0]
    for group in list(legs.vertex_groups):
        group.remove([vertex.index])
    for name in ("Hips", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "LeftToes"):
        legs.vertex_groups[name].add([vertex.index], 0.2, "REPLACE")


def main():
    global HANDLER
    out = arguments()
    os.makedirs(out, exist_ok=True)
    HANDLER = Handler(out, allow_python=False, desktop=False, autosave_seconds=None)
    cmd("new_scene")
    meshes, rig = character_models.hero(cmd)
    cmd("animation_preset", armature=rig, preset="walk")
    cmd("animation_preset", armature=rig, preset="idle")
    cmd("export", path="humanoid.glb", names=meshes)
    cmd("checkpoint", name="rigged")
    unweight_one_vertex()
    cmd("save_blend", path="unweighted.blend")
    cmd("restore_checkpoint", name="rigged")
    fifth_influence()
    cmd("save_blend", path="five-influences.blend")
    cmd("restore_checkpoint", name="rigged")
    end = cmd("clip_info", clip="walk")["clips"][0]["frame_end"]
    cmd("clip_keys", clip="walk", object=rig, bone="Hips", channel="location", keys=[{"frame": end, "value": [0.0, 0.05, 0.0]}], interpolation="linear")
    cmd("export", path="popping.glb", names=meshes)
    cmd("restore_checkpoint", name="rigged")
    cmd("bone_edit", armature=rig, bones=[{"name": "LeftHand", "rename": "Palm"}])
    cmd("export", path="renamed.glb", names=meshes)


main()
