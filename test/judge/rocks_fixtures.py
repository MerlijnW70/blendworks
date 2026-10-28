import os
import shutil
import sys
import tempfile

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

SIZE = [1.4, 1.0, 0.8]
REACH = max(SIZE)
ROCK_LAYERS = (
    {"amplitude": 0.24 * REACH, "seed": 7, "scale": 0.5 * REACH, "octaves": 2, "hurst": 0.7, "direction": "z"},
    {"amplitude": 0.02 * REACH, "seed": 8, "basis": "worley_f2_minus_f1", "mode": "ridged", "ridge_offset": 0.5, "scale": 0.3 * REACH, "octaves": 2, "hurst": 0.5},
    {"amplitude": 0.03 * REACH, "seed": 9, "scale": 0.13 * REACH, "octaves": 3, "hurst": 0.5},
)


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def value_noise(size, seed, octaves=6):
    rng = np.random.default_rng(seed)
    field = np.zeros((size, size))
    amplitude = 1.0
    for octave in range(octaves):
        cells = 4 * 2**octave
        lattice = rng.random((cells + 1, cells + 1))
        position = np.arange(size) * cells / size
        index = position.astype(int)
        fraction = position - index
        smooth = fraction * fraction * (3 - 2 * fraction)
        rows = lattice[index] * (1 - smooth)[:, None] + lattice[index + 1] * smooth[:, None]
        field += amplitude * (rows[:, index] * (1 - smooth)[None, :] + rows[:, index + 1] * smooth[None, :])
        amplitude *= 0.6
    field -= field.min()
    return field / field.max()


def texture(name):
    grey = 0.25 + 0.6 * value_noise(256, 7)
    image = bpy.data.images.new(f"{name}-albedo", 256, 256)
    rgba = np.ones((256, 256, 4), dtype=np.float32)
    rgba[:, :, :3] = grey[:, :, None]
    image.pixels.foreach_set(rgba.ravel())
    image.pack()
    material = bpy.data.materials.new(f"{name}-stone")
    tree = material.node_tree
    shader = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
    obj = bpy.data.objects[name]
    obj.data.materials.clear()
    obj.data.materials.append(material)


def handler():
    return Handler(tempfile.mkdtemp(prefix="blendworks-rocks-"), allow_python=False, desktop=False)


def run(bridge, command, /, **args):
    reply = bridge.handle({"cmd": command, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{command}: {reply['error']['message']}")
    return reply["result"]


def base(bridge, name, subdivisions):
    run(bridge, "add_primitive", type="ico_sphere", name=name, radius=0.5, subdivisions=subdivisions)
    run(bridge, "transform", name=name, scale=SIZE)
    run(bridge, "apply_transform", name=name, scale=True)


def finish(bridge, name):
    run(bridge, "shade_smooth", name=name)
    run(bridge, "uv_smart_project", name=name, island_margin=0.01)
    texture(name)
    run(bridge, "export", path=f"{name}.glb", names=[name])


def fractured_rock(bridge):
    base(bridge, "Block", 4)
    pieces = run(bridge, "fracture", name="Block", pieces=2, mode="binary", seed=7, min_size=0.4 * min(SIZE))
    keep = max(zip(pieces["pieces"], pieces["volumes"]), key=lambda entry: entry[1])[0]
    run(bridge, "delete", names=[name for name in pieces["pieces"] if name != keep])
    run(bridge, "rename", name=keep, new_name="FracturedRock")
    run(bridge, "chip", name="FracturedRock", count=6, depth=0.3 * REACH, seed=7)
    run(bridge, "abrade", name="FracturedRock", amount=1.0, seed=7)
    for layer in ROCK_LAYERS:
        run(bridge, "noise_displace", name="FracturedRock", **layer)
    finish(bridge, "FracturedRock")


def displaced_sphere(bridge):
    base(bridge, "DisplacedSphere", 6)
    run(bridge, "noise_displace", name="DisplacedSphere", amplitude=0.1, seed=3, mode="billow", scale=1.2, octaves=3, hurst=0.9)
    finish(bridge, "DisplacedSphere")


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    for build in (fractured_rock, displaced_sphere):
        bridge = handler()
        run(bridge, "new_scene")
        build(bridge)
        workspace = bridge.workspace.root
        for name in os.listdir(workspace):
            if name.endswith(".glb"):
                shutil.move(os.path.join(workspace, name), os.path.join(folder, name))


main()
