"""Build a scene through every command family that creates mesh topology (terrain, liquids, a glass, a tree with bark and
leaves, mesh data, booleans, voxel remesh, blobs, fractures, applied modifiers, scatter, rain, an OBJ round trip) and
write the exact digest of every object's data: all attributes, hidden ones such as edge vertices and corner edges
included. Run it at different thread counts with blender -t and compare the files.

blender --background --factory-startup -t <threads> --python bench/thread-scene/scene.py -- <out folder>"""
import json
import math
import os
import sys

import bpy
import numpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))
sys.path.insert(0, os.path.join(HERE, ".."))

from blendworks_bridge import Handler  # noqa: E402
from scene_digest import scene_digest  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(ARGS[0])
WIDE = "--wide" in ARGS
class Builder:
    def __init__(self, workspace):
        self.handler = Handler(workspace, allow_python=False, autosave_seconds=None)

    def __call__(self, name, /, **args):
        reply = self.handler.handle({"cmd": name, "args": args})
        if not reply["ok"]:
            raise RuntimeError(f"{name}: {reply['error']['message']}")
        return reply["result"]


def tumbler(top, bottom, height, wall, base):
    outer = [[0.0, 0.0], [bottom - 0.002, 0.0], [bottom, 0.0015], [top, height]]
    lip = [[top - wall / 2.0 + wall / 2.0 * math.cos(math.pi * k / 6), height + wall / 2.0 * math.sin(math.pi * k / 6)] for k in range(1, 6)]
    inner = [[top - wall, height], [bottom - wall * 1.4, base + 0.002], [bottom - wall * 1.4 - 0.003, base], [0.0, base]]
    return outer + lip + inner


def grid(count, size):
    steps = numpy.linspace(-size / 2.0, size / 2.0, count)
    xs, ys = numpy.meshgrid(steps, steps)
    vertices = numpy.stack([xs.ravel(), ys.ravel(), 0.2 * numpy.sin(xs.ravel() * 3.0) * numpy.cos(ys.ravel() * 2.0)], axis=1)
    first = (numpy.arange(count - 1)[None, :] + count * numpy.arange(count - 1)[:, None]).ravel()
    faces = numpy.stack([first, first + 1, first + count + 1, first + count], axis=1)
    sharp = [[int(index), int(index + 1)] for index in first[::7]]
    return vertices.round(6).tolist(), faces.tolist(), sharp


def build(cmd):
    cmd("new_scene")
    cmd("heightfield", name="land", size=[80.0, 80.0], resolution=97, height=6.0, seed=4, skirt=True)
    cmd("liquid_body", kind="lake", name="lake", ground=["land"], point=[0.0, 0.0, 0.0], seed=3)
    cmd("liquid_body", kind="river", name="river", ground=["land"], point=[30.0, 30.0, 0.0], width=3.0, depth=0.6, carve=False, wet_shore=False, seed=5)
    cmd("lathe", name="glass", profile=tumbler(0.04, 0.035, 0.11, 0.0025, 0.01), segments=96)
    cmd("transform", name="glass", location=[40.0, 0.0, 0.0])
    cmd("liquid_fill", container="glass", preset="water_fresh", fill=0.7, name="water", glass=True)
    cmd("grow_tree", name="birch", preset="birch", seed=7, location=[-30.0, -30.0, 0.0], limit=0)
    cmd("tree_mesh", name="birch")
    cmd("tree_leaves", name="birch_bark", seed=7, detail="low")
    vertices, faces, sharp = grid(48, 4.0)
    cmd("mesh_from_data", name="sheet", vertices=vertices, faces=faces, sharp_edges=sharp, location=[0.0, 40.0, 0.0])
    cmd("add_primitive", type="sphere", name="ball", radius=1.0, segments=64, rings=32, location=[10.0, 40.0, 0.0])
    cmd("add_primitive", type="cube", name="block", size=1.4, location=[10.5, 40.3, 0.4])
    cmd("boolean", name="ball", cutter="block", operation="difference", cutter_action="delete")
    cmd("add_primitive", type="torus", name="ring", location=[20.0, 40.0, 0.0])
    cmd("remesh", name="ring", voxel_size=0.04)
    cmd("blob", name="drop", points=[{"position": [30.0, 40.0, 0.0], "radius": 0.6}, {"position": [30.6, 40.0, 0.2], "radius": 0.5}, {"position": [30.2, 40.5, 0.5], "radius": 0.4}], voxel_size=0.03)
    cmd("add_primitive", type="ico_sphere", name="stone", radius=0.8, subdivisions=4, location=[40.0, 40.0, 0.0])
    cmd("fracture", name="stone", pieces=6, seed=2)
    cmd("add_primitive", type="cylinder", name="pipe", radius=0.5, depth=2.0, segments=128, location=[-10.0, 40.0, 0.0])
    cmd("add_modifier", name="pipe", solidify={"thickness": 0.05}, apply=True)
    cmd("add_primitive", type="sphere", name="pebble", radius=0.15, segments=12, rings=6, location=[0.0, 0.0, -50.0])
    cmd("scatter", target="land", source="pebble", min_distance=2.5, seed=6, max_count=300, name="pebbles", realize=True)
    cmd("weather", preset="light_rain", seed=2)
    cmd("export", path="sheet.obj", names=["sheet"])
    cmd("delete", names=["sheet"])
    cmd("import", path="sheet.obj")


def wide(cmd):
    cmd("add_primitive", type="cube", name="box", size=1.0, location=[0.0, -40.0, 0.0])
    cmd("subdivide", name="box", cuts=8)
    cmd("merge_by_distance", name="box", distance=0.001)
    cmd("add_primitive", type="cylinder", name="post", radius=0.3, depth=1.5, segments=48, location=[4.0, -40.0, 0.0])
    cmd("decimate", name="post", ratio=0.4, apply=True)
    cmd("clean_mesh", name="post")
    cmd("sweep", name="rail", preset="circle", radius=0.05, segments=12, helix={"radius": 0.5, "pitch": 0.3, "turns": 4.0}, location=[8.0, -40.0, 0.0])
    cmd("gear", name="cog", teeth=24, module=0.05, thickness=0.1, bore=0.2, chamfer=0.005, location=[12.0, -40.0, 0.0])
    cmd("shell", name="snail", location=[16.0, -40.0, 0.0], size=0.5)
    cmd("extrude_outline", name="plate", outline=[[0.0, 0.0], [1.0, 0.0], [1.0, 0.6], [0.0, 0.6]], holes=[[[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.4]]], depth=0.05, chamfer=0.005, location=[20.0, -40.0, 0.0])
    cmd("engrave", name="plate", text="BW", plane={"origin": [20.5, -39.7, 0.05], "normal": [0.0, 0.0, 1.0]}, size=0.2, depth=0.01)
    cmd("add_primitive", type="cube", name="rock", size=1.0, location=[24.0, -40.0, 0.0])
    cmd("chip", name="rock", count=3, depth=0.08, seed=3)
    cmd("abrade", name="rock", amount=0.3, seed=3)
    cmd("heightfield", name="hill", size=[20.0, 20.0], resolution=65, height=3.0, seed=9)
    cmd("transform", name="hill", location=[0.0, -70.0, 0.0])
    cmd("erode", name="hill", droplets=3000, iterations=20, seed=2)
    cmd("noise_displace", name="hill", amplitude=0.1, seed=4, direction="z")
    cmd("uv_smart_project", name="hill")
    cmd("generate_lods", names=["rock"], count=2, ratios=[0.5, 0.25])
    cmd("ground_cover", target="hill", populations=[{"name": "grass", "element": "grass", "density": 0.1, "variants": 2, "triangles": 60}, {"name": "tufts", "element": "tuft", "density": 0.05, "variants": 1, "form": "cards"}], seed=3, realize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    cmd = Builder(OUT)
    build(cmd)
    if WIDE:
        wide(cmd)
    bpy.context.view_layer.update()
    digest = scene_digest()
    with open(os.path.join(OUT, "digest.json"), "w", encoding="utf-8") as handle:
        json.dump({"objects": digest}, handle, indent=1, sort_keys=True)
    print(f"THREAD-SCENE {len(digest)} objects", flush=True)


main()
