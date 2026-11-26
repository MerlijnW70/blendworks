FIXTURE_DEPS = ("bridge/blendworks_bridge",)
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import bpy
import numpy
from mathutils import Matrix

from blendworks_bridge import Handler
from blendworks_bridge.tree_skeleton import PROPERTY, plain

SPECIES = ("oak", "birch", "pine", "willow", "maple", "olive")
SPACING = 16.0
GRID = 4
SKELETON_DIGITS = 7


def on_grid(names):
    for name in names:
        obj = bpy.data.objects[name]
        if obj.type != "MESH":
            continue
        points = numpy.zeros(3 * len(obj.data.vertices))
        obj.data.vertices.foreach_get("co", points)
        obj.data.vertices.foreach_set("co", numpy.round(points, GRID))
        obj.data.update()
        if PROPERTY in obj:
            skeleton = plain(obj[PROPERTY])
            for key in ("position", "radius"):
                skeleton[key] = [round(value, SKELETON_DIGITS + (2 if key == "radius" else 0)) for value in skeleton[key]]
            obj[PROPERTY] = skeleton


def snap_copies(parent):
    """Put every linked copy on a 1/64 m grid and a right-angle turn about Z, whose matrices every platform writes alike."""
    for copy in bpy.data.objects[parent].children:
        matrix = copy.matrix_world
        quarter = round(math.atan2(matrix[1][0], matrix[0][0]) / (0.5 * math.pi))
        snapped = Matrix.Rotation(quarter * 0.5 * math.pi, 4, "Z")
        snapped.translation = [round(value * 64.0) / 64.0 for value in matrix.translation]
        copy.matrix_world = snapped
    for mesh in bpy.data.meshes:
        if "_cluster_" in mesh.name:
            points = numpy.zeros(3 * len(mesh.vertices))
            mesh.vertices.foreach_get("co", points)
            mesh.vertices.foreach_set("co", numpy.round(points, GRID))
            mesh.update()


def main():
    folder = sys.argv[sys.argv.index("--") + 1 :][0]
    os.makedirs(folder, exist_ok=True)
    handler = Handler(folder, allow_python=False, desktop=False)

    def cmd(name, /, **args):
        reply = handler.handle({"cmd": name, "args": args})
        if not reply["ok"]:
            raise RuntimeError(f"{name}: {reply['error']['message']}")
        return reply["result"]

    cmd("new_scene")
    barks = []
    for index, species in enumerate(SPECIES):
        cmd("grow_tree", name=species, preset=species, seed=index + 1, location=[SPACING * index, 0.0, 0.0], limit=0)
        bark = cmd("tree_mesh", name=species, ring_segments={"min": 5, "max": 10, "per_metre": 12.0}, rings_per_segment=1)["name"]
        barks.append(bark)
    on_grid(barks)
    cmd("export", path="barks.glb", names=barks)
    cmd("new_scene")
    cmd("grow_tree", name="maple", preset="maple", seed=4, limit=0)
    bark = cmd("tree_mesh", name="maple", ring_segments={"min": 5, "max": 10, "per_metre": 12.0}, rings_per_segment=1)["name"]
    linked = cmd("tree_leaves", name=bark, seed=4, realize=False)["name"]
    on_grid([bark])
    snap_copies(linked)
    cmd("export", path="linked.glb")
    shutil.rmtree(os.path.join(folder, ".blendworks"), ignore_errors=True)


main()
