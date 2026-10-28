FIXTURE_DEPS = ("bridge/blendworks_bridge",)
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "bridge"))
sys.path.insert(0, os.path.join(ROOT, "docs", "examples"))

import bmesh
import bpy
from mathutils import Matrix, Vector

import grow_trees
import tree_meshes
from blendworks_bridge import Handler


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def cylinder(bm, start, end, radius):
    axis = end - start
    matrix = Matrix.Translation((start + end) / 2) @ axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=radius, radius2=radius * 0.7, depth=axis.length, matrix=matrix)


def cylinder_tree():
    bm = bmesh.new()
    trunk_top = Vector((0.0, 0.0, 1.2))
    cylinder(bm, Vector((0.0, 0.0, 0.0)), trunk_top, 0.08)
    for branch in range(3):
        angle = branch * 2.0 * math.pi / 3.0
        tip = trunk_top + Vector((math.cos(angle) * 0.6, math.sin(angle) * 0.6, 0.5))
        cylinder(bm, trunk_top, tip, 0.04)
        for twig in range(12):
            turn = angle + (twig - 5.5) * 0.25
            base = trunk_top.lerp(tip, 0.3 + 0.06 * twig)
            cylinder(bm, base, base + Vector((math.cos(turn) * 0.3, math.sin(turn) * 0.3, 0.25)), 0.012)
    mesh = bpy.data.meshes.new("CylinderTree")
    bm.to_mesh(mesh)
    bm.free()
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("CylinderTree", mesh))


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    handler = Handler(folder, allow_python=False, desktop=False)

    def cmd(name, /, **args):
        reply = handler.handle({"cmd": name, "args": args})
        if not reply["ok"]:
            raise RuntimeError(f"{name}: {reply['error']['message']}")
        return reply["result"]

    cmd("new_scene")
    grow_trees.trees(cmd, 1.0)
    cmd("tree_mesh", name="oak", **tree_meshes.MESH["oak"])
    cmd("export", path="oak-bark.glb", names=["oak_bark"])
    cmd("new_scene")
    cylinder_tree()
    cmd("export", path="cylinder-tree.glb", names=["CylinderTree"])
    shutil.rmtree(os.path.join(folder, ".blendworks"), ignore_errors=True)


main()
