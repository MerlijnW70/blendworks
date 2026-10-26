import base64
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run, snapshot

WIDTH = 8
HEIGHT = 4


def rgbe(red, green, blue):
    brightest = max(red, green, blue)
    if brightest < 1e-32:
        return bytes((0, 0, 0, 0))
    mantissa, exponent = math.frexp(brightest)
    scale = mantissa * 256.0 / brightest
    return bytes((int(red * scale), int(green * scale), int(blue * scale), exponent + 128))


def write_hdr(path, top, bottom):
    header = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {HEIGHT} +X {WIDTH}\n".encode("ascii")
    rows = []
    for row in range(HEIGHT):
        colour = top if row < HEIGHT // 2 else bottom
        rows.append(rgbe(*colour) * WIDTH)
    with open(path, "wb") as handle:
        handle.write(header + b"".join(rows))


def world_nodes():
    tree = bpy.context.scene.world.node_tree
    return {node.type: node for node in tree.nodes}


def linked(tree, from_node, to_node):
    return any(link.from_node == from_node and link.to_node == to_node for link in tree.links)


def test_set_world_hdri_builds_an_environment_world(bridge):
    write_hdr(os.path.join(bridge.workspace, "sky.hdr"), (1.0, 0.5, 0.25), (0.125, 0.125, 0.125))
    result = bridge.ok("set_world_hdri", path="sky.hdr", strength=2.5, rotation=90.0)
    assert result["path"] == "sky.hdr"
    assert (result["width"], result["height"]) == (WIDTH, HEIGHT)
    assert result["strength"] == 2.5 and result["rotation"] == 90.0
    world = bpy.context.scene.world
    assert world.name == result["world"]
    nodes = world_nodes()
    environment = nodes["TEX_ENVIRONMENT"]
    assert environment.image.name == result["image"] == "sky.hdr"
    assert environment.projection == "EQUIRECTANGULAR"
    assert os.path.normcase(bpy.path.abspath(environment.image.filepath)) == os.path.normcase(os.path.join(bridge.workspace, "sky.hdr"))
    close(nodes["BACKGROUND"].inputs["Strength"].default_value, 2.5)
    close(list(nodes["MAPPING"].inputs["Rotation"].default_value), [0.0, 0.0, math.radians(90.0)])
    tree = world.node_tree
    assert linked(tree, nodes["TEX_COORD"], nodes["MAPPING"])
    assert linked(tree, nodes["MAPPING"], environment)
    assert linked(tree, environment, nodes["BACKGROUND"])
    assert linked(tree, nodes["BACKGROUND"], nodes["OUTPUT_WORLD"])


def test_set_world_hdri_reads_the_pixels(bridge):
    write_hdr(os.path.join(bridge.workspace, "sky.hdr"), (1.0, 0.5, 0.25), (0.125, 0.125, 0.125))
    bridge.ok("set_world_hdri", path="sky.hdr")
    image = world_nodes()["TEX_ENVIRONMENT"].image
    pixels = list(image.pixels)
    bottom_row_in_blender = pixels[0:4]
    top_row_in_blender = pixels[(HEIGHT - 1) * WIDTH * 4 : (HEIGHT - 1) * WIDTH * 4 + 4]
    close(top_row_in_blender, [1.0, 0.5, 0.25, 1.0], 0.01)
    close(bottom_row_in_blender, [0.125, 0.125, 0.125, 1.0], 0.01)
    assert world_nodes()["BACKGROUND"].inputs["Strength"].default_value == 1.0


def mean_brightness(result):
    data = base64.b64decode(result["images"][0]["data"])
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    try:
        with open(path, "wb") as out:
            out.write(data)
        image = bpy.data.images.load(path, check_existing=False)
        pixels = list(image.pixels)
        bpy.data.images.remove(image)
    finally:
        os.remove(path)
    values = [value for index, value in enumerate(pixels) if index % 4 != 3]
    return sum(values) / len(values)


def render_lit_by(bridge, name, colour):
    write_hdr(os.path.join(bridge.workspace, name), colour, colour)
    bridge.ok("set_world_hdri", path=name)
    return mean_brightness(bridge.ok("render_preview", camera="Cam", resolution=64, samples=4))


def test_a_render_is_lit_by_the_hdri(bridge):
    bridge.ok("add_primitive", type="sphere", name="Ball")
    bridge.ok("add_light", type="point", name="Off", energy=0.0)
    bridge.ok("add_camera", name="Cam", location=[0.0, -4.0, 0.0], target=[0.0, 0.0, 0.0])
    dark = render_lit_by(bridge, "dark.hdr", (0.02, 0.02, 0.02))
    bright = render_lit_by(bridge, "bright.hdr", (0.8, 0.8, 0.8))
    assert bright > dark * 5 and bright > 0.3, (dark, bright)


def test_set_world_hdri_refuses_bad_paths_and_files(bridge):
    write_hdr(os.path.join(bridge.workspace, "sky.hdr"), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0))
    with open(os.path.join(bridge.workspace, "broken.hdr"), "wb") as handle:
        handle.write(b"not an image at all")
    with open(os.path.join(bridge.workspace, "sky.png"), "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
    before = snapshot()
    images = sorted(image.name for image in bpy.data.images)
    worlds = sorted(world.name for world in bpy.data.worlds)
    bridge.refuse("set_world_hdri", "forbidden", path="../outside.hdr")
    bridge.refuse("set_world_hdri", "forbidden", path="sky.png")
    bridge.refuse("set_world_hdri", "not_found", path="missing.exr")
    bridge.refuse("set_world_hdri", "failed", path="broken.hdr")
    bridge.refuse("set_world_hdri", "bad_args", path="sky.hdr", strength=-1.0)
    bridge.refuse("set_world_hdri", "bad_args", path="sky.hdr", rotation=400.0)
    bridge.refuse("set_world_hdri", "bad_args", path="sky.hdr", tint=[1.0, 0.0, 0.0])
    assert snapshot() == before
    assert sorted(image.name for image in bpy.data.images) == images
    assert sorted(world.name for world in bpy.data.worlds) == worlds


run(globals())
