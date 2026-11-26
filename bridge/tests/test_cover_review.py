import base64
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from blendworks_bridge.commands.ground_export import level_vertices
from blendworks_bridge.cover_kinds import element_materials, element_params
from cover_helpers import attribute_of, glb_document, instanced_translations, make_plane, points_of, workspace_file

def pixels(image):
    path = os.path.join(tempfile.mkdtemp(prefix="blendworks-png-"), "view.png")
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(image["data"]))
    loaded = bpy.data.images.load(path)
    try:
        width, height = loaded.size
        values = list(loaded.pixels)
    finally:
        bpy.data.images.remove(loaded)
    return width, height, values


LIMIT = 2_000_000
RENDER = 64
HEAVY = [{"name": "grass", "element": "grass", "density": 40.0, "form": "geometry", "variants": 1, "triangles": 400}]


def matrices_of(name):
    return attribute_of(name, "gc_transform", 16).reshape(-1, 4, 4).transpose(0, 2, 1)


def test_realizing_more_vertices_than_the_limit_is_refused_before_anything_is_built(bridge):
    make_plane(bridge, size=20.0)
    meshes = len(bpy.data.meshes)
    message = bridge.refuse("ground_cover", "bad_args", target="Ground", populations=HEAVY, seed=1, realize=True)
    assert "would make" in message and "instances" in message
    assert "GroundCover" not in bpy.data.objects and len(bpy.data.meshes) == meshes
    kept = bridge.ok("ground_cover", target="Ground", populations=HEAVY, seed=1)
    assert kept["count"] * len(bpy.data.objects["GroundCover_grass_e000"].data.vertices) > LIMIT
    meshes = len(bpy.data.meshes)
    message = bridge.refuse("ground_cover_export", "bad_args", path="big.glb", name="GroundCover", mode="realized", levels=1)
    assert "LOD0 would have" in message
    assert len(bpy.data.meshes) == meshes and not any("_LOD" in name for name in bpy.data.objects.keys())
    assert not os.path.exists(workspace_file(bridge, "big.glb"))
    bridge.ok("ground_cover_export", path="big.glb", name="GroundCover", mode="instances")


def test_the_vertex_estimate_for_realized_levels_matches_what_is_realized(bridge):
    make_plane(bridge, size=6.0)
    populations = [
        {"name": "grass", "element": "grass", "density": 3.0, "variants": 2, "form": "auto", "card_distance": 2.0, "triangles": 120},
        {"name": "stones", "element": "pebble", "density": 1.0, "variants": 2, "triangles": 80},
    ]
    bridge.ok("ground_cover", target="Ground", populations=populations, point=[0.0, -3.0, 1.0], near=2.0, seed=4)
    result = bridge.ok("ground_cover_export", path="lods.glb", name="GroundCover", mode="realized", levels=3)
    for name in ("GroundCover_grass", "GroundCover_stones"):
        cards = bool(bpy.data.objects[name].get("gc_has_cards", False))
        for level in range(3):
            assert level_vertices(bpy.data.objects[name], level, cards) == result["levels"][f"{name}_LOD{level}"]["vertices"], (name, level)


def test_scale_range_sets_the_size_of_every_instance(bridge):
    make_plane(bridge, size=20.0)
    populations = [{"name": "stones", "element": "pebble", "density": 3.0, "variants": 1, "scale_range": [0.5, 2.0], "align": 0.0, "tilt": 0.0}]
    bridge.ok("ground_cover", target="Ground", populations=populations, seed=2)
    scales = numpy.linalg.norm(matrices_of("GroundCover_stones")[:, :3, 2], axis=1)
    assert len(scales) > 800
    assert scales.min() >= 0.5 - 1e-3 and scales.max() <= 2.0 + 1e-3
    assert scales.min() < 0.55 and scales.max() > 1.95
    assert abs(scales.mean() - 1.25) < 0.06, scales.mean()


def test_grass_tilts_with_the_slope_in_proportion_to_align(bridge):
    make_plane(bridge, size=20.0)
    bridge.ok("transform", name="Ground", rotation=[30.0, 0.0, 0.0])
    angles = {}
    for align in (0.0, 0.5, 1.0):
        name = f"Cover{int(align * 10)}"
        populations = [{"name": "grass", "element": "grass", "density": 2.0, "variants": 1, "form": "cards", "align": align, "tilt": 0.0}]
        bridge.ok("ground_cover", target="Ground", name=name, populations=populations, seed=3)
        axes = matrices_of(f"{name}_grass")[:, :3, 2]
        axes = axes / numpy.linalg.norm(axes, axis=1)[:, None]
        angles[align] = float(numpy.median(numpy.degrees(numpy.arccos(numpy.clip(axes[:, 2], -1.0, 1.0)))))
    assert angles[0.0] < 1.0, angles
    assert 12.0 < angles[0.5] < 18.0, angles
    assert 27.0 < angles[1.0] < 33.0, angles


def blade(bridge, name, **params):
    base = {"blades": 1, "height": [0.4, 0.4], "width": 0.04, "spread": 0.0, "twist": 0.0, "lean": 0.0, "curvature": 0.0, "dry_tips": 0.0}
    bridge.ok("ground_element", kind="grass", name=name, triangles=40, seed=3, params=dict(base, **params))
    mesh = bpy.data.objects[name].data
    values = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", values)
    return values.reshape(-1, 3)


def test_blade_width_tapers_towards_the_tip(bridge):
    for taper, low, high in ((0.9, 0.0, 0.3), (0.0, 0.85, 1.2)):
        points = blade(bridge, f"Taper{int(taper * 10)}", taper=taper)
        widths = numpy.linalg.norm(points[1:-1:2] - points[0:-1:2], axis=1)
        assert low <= widths[-1] / widths[1] <= high, (taper, widths)


def test_blade_curvature_bends_the_tip_over(bridge):
    straight = blade(bridge, "Straight", curvature=0.0)
    arched = blade(bridge, "Arched", curvature=1.0)

    def tip_angle(points):
        direction = points[-1] - 0.5 * (points[-2] + points[-3])
        return math.degrees(math.atan2(math.hypot(direction[0], direction[1]), direction[2]))

    assert tip_angle(straight) < 2.0
    assert tip_angle(arched) > 35.0, tip_angle(arched)
    assert arched[:, 2].max() < straight[:, 2].max() - 0.01


def object_pixels(bridge, name, direction):
    result = bridge.ok("render_preview", resolution=RENDER, samples=8, device="cpu", focus={"object": name, "direction": direction})
    width, height, values = pixels(result["images"][0])
    image = numpy.array(values).reshape(height, width, 4)[::-1, :, :3]
    return image, numpy.linalg.norm(image - image[2, 2], axis=2) > 0.06


def test_blade_colour_runs_from_a_dark_root_to_a_lighter_tip(bridge):
    blade(bridge, "Ribbon", width=0.1, taper=0.0)
    best = None
    for direction in ([0.0, -1.0, 0.0], [1.0, 0.0, 0.0]):
        image, mask = object_pixels(bridge, "Ribbon", direction)
        if best is None or mask.sum() > best[1].sum():
            best = (image, mask)
    image, mask = best
    rows = numpy.nonzero(mask.any(axis=1))[0]
    span = rows.max() - rows.min()
    assert span > 20
    tip, root = mask.copy(), mask.copy()
    tip[rows.min() + span // 4 :] = False
    root[: rows.min() + 3 * span // 4] = False
    assert root.sum() > 20 and tip.sum() > 20
    assert image[tip][:, 1].mean() > 1.15 * image[root][:, 1].mean(), (image[tip].mean(axis=0), image[root].mean(axis=0))


def test_the_instance_tint_changes_the_shaded_colour(bridge):
    make_plane(bridge, size=2.0)
    bridge.ok("add_camera", name="Down", location=[0.0, 0.0, 1.0])
    bridge.ok("transform", name="Down", rotation=[0.0, 0.0, 0.0])
    populations = [{"name": "grass", "element": "grass", "density": 400.0, "variants": 1, "form": "cards", "color_variation": 1.0, "params": {"height": [0.1, 0.1]}}]
    bridge.ok("ground_cover", target="Ground", populations=populations, seed=1, darken=0.0)
    cover = bpy.data.objects["GroundCover_grass"]
    greenness = {}
    for tint in (-0.9, 0.9):
        cover.data.attributes["gc_tint"].data.foreach_set("value", numpy.full(len(cover.data.vertices), tint, dtype=numpy.float32))
        cover.data.update()
        cover.update_tag()
        bpy.context.view_layer.update()
        result = bridge.ok("render_preview", camera="Down", resolution=RENDER, samples=8, device="cpu")
        _, _, values = pixels(result["images"][0])
        mean = numpy.array(values).reshape(-1, 4)[:, :3].mean(axis=0)
        greenness[tint] = mean[1] - 0.5 * (mean[0] + mean[2])
    assert greenness[0.9] > greenness[-0.9] + 0.02, greenness


def test_existing_materials_are_never_overwritten(bridge):
    make_plane(bridge, size=4.0)
    taken = bpy.data.materials.new("GroundCover_grass_grass_geometry_0")
    taken.use_nodes = True
    nodes, colour = len(taken.node_tree.nodes), tuple(taken.diffuse_color)
    populations = [{"name": "grass", "element": "grass", "density": 2.0, "form": "geometry", "variants": 1}]
    assert "already exists" in bridge.refuse("ground_cover", "bad_args", target="Ground", populations=populations)
    assert len(taken.node_tree.nodes) == nodes and tuple(taken.diffuse_color) == colour
    assert "GroundCover" not in bpy.data.objects
    bpy.data.materials.new("Blade_grass_geometry_0")
    assert "already exists" in bridge.refuse("ground_element", "bad_args", kind="grass", name="Blade")
    assert "Blade" not in bpy.data.objects


def blade_shares(material):
    return sorted(node.inputs[1].default_value for node in material.node_tree.nodes if node.type == "MATH" and node.operation == "MULTIPLY" and node.inputs[0].is_linked and 0.4 < node.inputs[1].default_value < 1.0)


def test_variants_whose_cards_differ_in_width_get_their_own_material(bridge):
    params = element_params("grass", {"width": 0.004})
    cache = {}
    narrow = element_materials("Var", "grass", "cards", params, {"card_width": 0.2}, cache)[0]
    again = element_materials("Var", "grass", "cards", params, {"card_width": 0.2}, cache)[0]
    wide = element_materials("Var", "grass", "cards", params, {"card_width": 0.02}, cache)[0]
    assert narrow is again and narrow is not wide
    assert blade_shares(narrow) != blade_shares(wide)
    make_plane(bridge, size=4.0)
    populations = [{"name": "grass", "element": "grass", "density": 2.0, "form": "cards", "variants": 4}]
    bridge.ok("ground_cover", target="Ground", populations=populations, seed=1)
    cards = bpy.data.collections["GroundCover_elements"].children[0].objects
    assert len({obj.data.materials[0].name for obj in cards}) == 1


def test_an_orthographic_camera_keeps_what_is_inside_its_frame(bridge):
    make_plane(bridge, size=30.0)
    bridge.ok("add_camera", name="Top", location=[0.0, 0.0, 30.0])
    camera = bpy.data.objects["Top"]
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 10.0
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 256
    populations = [{"name": "grass", "element": "grass", "density": 2.0, "form": "cards", "variants": 1}]
    bridge.ok("ground_cover", target="Ground", populations=populations, camera="Top", near=100.0, view_only=True, view_margin=0.0, seed=1)
    points = points_of("GroundCover_grass")
    assert len(points) > 0.8 * 2.0 * 100.0
    assert numpy.abs(points[:, :2]).max() <= 5.0 + 1e-3
    assert numpy.abs(points[:, :2]).max() > 4.8


def surface_area_within(name, region):
    mesh = bpy.data.objects[name].data
    mesh.calc_loop_triangles()
    corners = numpy.array([[mesh.vertices[index].co[:] for index in triangle.vertices] for triangle in mesh.loop_triangles])
    inside = numpy.all(numpy.abs(corners.mean(axis=1)[:, :2]) <= region, axis=1)
    cross = numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return 0.5 * numpy.linalg.norm(cross[inside], axis=1).sum()


def test_clumped_cover_keeps_its_declared_density_on_rough_terrain(bridge):
    bridge.ok("heightfield", name="Hills", size=[40.0, 40.0], resolution=161, height=3.0, scale=6.0, octaves=3, seed=3)
    populations = [{"name": "tufts", "element": "tuft", "density": 6.0, "variants": 1, "form": "cards", "clumping": {"radius": 0.6, "per_clump": 8.0}, "slope": [0.0, 180.0]}]
    bridge.ok("ground_cover", target="Hills", populations=populations, seed=9)
    points = points_of("GroundCover_tufts")
    inside = numpy.all(numpy.abs(points[:, :2]) <= 14.0, axis=1)
    density = inside.sum() / surface_area_within("Hills", 14.0)
    assert abs(density - 6.0) <= 0.1 * 6.0, density


def test_export_carries_the_instance_tint_and_applies_the_modifiers_of_other_objects(bridge):
    make_plane(bridge, size=6.0, cuts=2)
    populations = [{"name": "grass", "element": "grass", "density": 4.0, "form": "cards", "variants": 2, "color_variation": 0.5}]
    bridge.ok("ground_cover", target="Ground", populations=populations, seed=2)
    ground = bpy.data.objects["Ground"]
    plain = len(ground.data.vertices)
    ground.modifiers.new("Smooth", "SUBSURF").levels = 1
    bridge.ok("ground_cover_export", path="tint.glb", name="GroundCover", with_objects=["Ground"])
    document, binary = glb_document(workspace_file(bridge, "tint.glb"))
    tints = []
    for node in document["nodes"]:
        extension = node.get("extensions", {}).get("EXT_mesh_gpu_instancing")
        if extension:
            accessor = document["accessors"][extension["attributes"]["_GC_TINT"]]
            view = document["bufferViews"][accessor["bufferView"]]
            start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            tints.append(numpy.frombuffer(binary, dtype="<f4", count=accessor["count"], offset=start))
    exported = numpy.sort(numpy.concatenate(tints))
    assert numpy.allclose(exported, numpy.sort(attribute_of("GroundCover_grass", "gc_tint")), atol=1e-6)
    assert exported.std() > 0.1 and len(exported) == len(instanced_translations(document, binary))
    ground_node = next(node for node in document["nodes"] if node.get("name") == "Ground")
    positions = document["meshes"][ground_node["mesh"]]["primitives"][0]["attributes"]["POSITION"]
    assert document["accessors"][positions]["count"] > plain
    bridge.ok("ground_cover_export", path="lods_tint.glb", name="GroundCover", mode="realized", levels=1)
    document, _ = glb_document(workspace_file(bridge, "lods_tint.glb"))
    assert any(key.endswith("GC_TINT") for mesh in document["meshes"] for primitive in mesh["primitives"] for key in primitive["attributes"])


def test_the_budget_has_a_documented_maximum(bridge):
    make_plane(bridge, size=4.0)
    populations = [{"name": "grass", "element": "grass", "density": 1.0, "form": "cards", "variants": 1}]
    assert "at most 5000000" in bridge.refuse("ground_cover", "bad_args", target="Ground", populations=populations, budget=5_000_001)
    assert bridge.ok("ground_cover", target="Ground", populations=populations, budget=5_000_000)["budget"] == 5_000_000


run(globals())
