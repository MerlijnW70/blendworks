import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy
from mathutils import Vector
from mathutils.geometry import intersect_point_tri

from harness import run
from texture_helpers import world_state
from texture_stats import gradient_share, vein_statistics

from blendworks_bridge.presets import PRESETS

SIZE = 512
BAND_SIZE = 1024
CROP = 48
BEVEL = 0.006
RED = [0.6, 0.05, 0.05]
FLAT_BLUE_WOOD = {"light_color": [0.05, 0.1, 0.6], "dark_color": [0.05, 0.1, 0.6]}
WORN = {"color": [0.6, 0.38, 0.1], "roughness": 0.32, "wear": 0.3, "scratch_scale": 2.0, "bump": 0.02}


def channel(name, size):
    return numpy.array(bpy.data.images[name].pixels[:], dtype=numpy.float64).reshape(size, size, 4)


def bake(bridge, material, obj, channels, size=SIZE, samples=8):
    bridge.ok("assign_material", name=obj, material=material)
    bridge.ok(
        "bake",
        names=[obj],
        channels=channels,
        size=size,
        overwrite=True,
        samples={key: samples for key in channels},
        prefix="Swatch",
        device="cpu",
        margin=0,
        float_buffer=True,
        time_limit=600.0,
    )
    return {key: channel(f"Swatch_{key}", size) for key in channels}


def facing_plane(bridge, rotation):
    bridge.ok("add_primitive", type="plane", name="Plate", size=0.4, rotation=rotation)
    bridge.ok("apply_transform", name="Plate")
    bridge.ok("uv_smart_project", name="Plate")


def roughness_share(bridge):
    baked = bake(bridge, "Metal", "Plate", ["roughness"])
    return gradient_share(baked["roughness"][..., 0][CROP:-CROP, CROP:-CROP])


def band_crops(bridge, material, channels, size=BAND_SIZE):
    bridge.ok("add_primitive", type="cylinder", name="Band", radius=0.1, depth=0.02, segments=192)
    baked = bake(bridge, material, "Band", channels, size=size)
    mesh = bpy.data.objects["Band"].data
    uv = mesh.uv_layers.active.data
    points = [uv[index].uv for poly in mesh.polygons if abs(poly.normal.z) < 0.5 for index in poly.loop_indices]
    x0, x1 = int(min(point[0] for point in points) * size) + 24, int(max(point[0] for point in points) * size) - 24
    y0, y1 = int(min(point[1] for point in points) * size) + 24, int(max(point[1] for point in points) * size) - 24
    return {key: value[y0:y1, x0:x1] for key, value in baked.items()}


def barycentric(point, a, b, c):
    v0, v1, v2 = b - a, c - a, point - a
    d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
    denominator = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    return 1.0 - v - w, v, w


def uv_of(mesh, polygon, point):
    layer = mesh.uv_layers.active.data
    corners = [(mesh.vertices[mesh.loops[index].vertex_index].co, Vector((*layer[index].uv, 0.0))) for index in polygon.loop_indices]
    for a, b, c in [(0, 1, 2)] + ([(0, 2, 3)] if len(corners) == 4 else []):
        if intersect_point_tri(point, corners[a][0], corners[b][0], corners[c][0]) is not None:
            weights = barycentric(point, corners[a][0], corners[b][0], corners[c][0])
            return sum((weight * corners[index][1] for weight, index in zip(weights, (a, b, c))), Vector((0.0, 0.0, 0.0)))
    raise AssertionError("the point is outside the polygon")


def profile(mesh, polygon, image, start, direction, length, count, size=BAND_SIZE):
    values = []
    for step in range(count):
        point = Vector(start) + Vector(direction) * (length * (step + 0.5) / count)
        uv = uv_of(mesh, polygon, point)
        values.append(image[int(uv.y * size), int(uv.x * size), :3])
    return numpy.array(values)


def srgb(value):
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def bevelled_box(bridge, material):
    bridge.ok("add_primitive", type="cube", name="Box", size=0.2)
    bridge.ok("bevel", name="Box", width=BEVEL, segments=1)
    bridge.ok("uv_smart_project", name="Box")
    baked = bake(bridge, material, "Box", ["base_color"], size=BAND_SIZE)
    mesh = bpy.data.objects["Box"].data
    top = max(mesh.polygons, key=lambda polygon: polygon.normal.z * 10 + polygon.area)
    return profile(mesh, top, baked["base_color"], (0.1 - BEVEL, 0.0, 0.1), (-1.0, 0.0, 0.0), 0.04, 40)


def corner(bridge, material):
    bridge.ok("mesh_from_data", name="Corner", vertices=[[0, 0, 0], [0.2, 0, 0], [0.2, 0.2, 0], [0, 0.2, 0], [0, 0, 0.2], [0, 0.2, 0.2]], faces=[[0, 1, 2, 3], [0, 3, 5, 4]])
    bridge.ok("uv_smart_project", name="Corner")
    baked = bake(bridge, material, "Corner", ["base_color"], size=BAND_SIZE)
    mesh = bpy.data.objects["Corner"].data
    floor = max(mesh.polygons, key=lambda polygon: polygon.normal.z)
    return profile(mesh, floor, baked["base_color"], (0.0, 0.1, 0.0), (1.0, 0.0, 0.0), 0.05, 25)


def near_and_far(values, channel_index=None):
    reduced = values.mean(axis=1) if channel_index is None else values[:, channel_index]
    return float(reduced[:3].mean()), float(reduced[len(reduced) // 2 :].mean())


def test_wear_stays_smooth_on_faces_that_look_along_the_scratch_axis(bridge):
    for name, params in (("worn_metal", dict(WORN, scratch_direction="x")), ("brass", {"scratch_direction": "x", "polish": 0.2})):
        shares = []
        for rotation in ([0.0, 90.0, 0.0], [0.0, 0.0, 0.0]):
            bridge.ok("new_scene")
            facing_plane(bridge, rotation)
            bridge.ok("material_procedural", name="Metal", **{name: params})
            shares.append(roughness_share(bridge))
        facing, along = shares
        assert facing <= 0.03, (name, "a face that looks along the scratch axis must stay smooth", facing)
        assert along >= 0.1 and along >= 5 * facing, (name, "scratches must show on a face that contains the axis", along, facing)


def test_a_polished_brass_band_is_smooth_and_scratches_run_around_it(bridge):
    bridge.ok("material_procedural", name="Polished", brass={"polish": 1.0, "patina": 0.0})
    bridge.ok("material_procedural", name="Scratched", brass={"polish": 0.2, "patina": 0.0, "scratch_direction": "around_z"})
    polished = band_crops(bridge, "Polished", ["base_color", "roughness"])
    rough, colour = polished["roughness"][..., 0], polished["base_color"][..., 0]
    assert rough.std() <= 0.004 and gradient_share(rough) <= 0.03 and colour.std() <= 0.03, (rough.std(), gradient_share(rough), colour.std())
    bridge.ok("delete", names=["Band"])
    scratched = band_crops(bridge, "Scratched", ["roughness"])["roughness"][..., 0]
    assert scratched.std() >= 5 * rough.std() and gradient_share(scratched) >= 0.1, (scratched.std(), gradient_share(scratched))
    assert vein_statistics(scratched)["orientation"] >= 0.4, vein_statistics(scratched)


def test_brass_edges_stay_bright_and_wear_concentrates_on_a_bevelled_edge(bridge):
    bridge.ok("material_procedural", name="Metal", brass={"polish": 0.8})
    near, far = near_and_far(bevelled_box(bridge, "Metal"))
    assert near >= 1.1 * far, (near, far)


def test_the_edge_mask_of_a_layer_follows_a_bevel_and_not_the_flat_face(bridge):
    bridge.ok("add_material", name="Paint", base_color=RED, roughness=0.4)
    bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, mask="edges", amount=0.5, softness=0.2, distance=0.02, breakup=0.0)
    near, far = near_and_far(bevelled_box(bridge, "Paint"), channel_index=2)
    assert near >= 0.6 and far <= 0.3, (near, far)


def test_the_cavity_mask_of_a_layer_follows_a_concave_corner(bridge):
    bridge.ok("add_material", name="Paint", base_color=RED, roughness=0.4)
    bridge.ok("material_layer", material="Paint", wood=FLAT_BLUE_WOOD, mask="cavity", amount=0.5, softness=0.2, distance=0.02, breakup=0.0)
    near, far = near_and_far(corner(bridge, "Paint"), channel_index=2)
    assert near >= 0.6 and far <= 0.3, (near, far)


def test_patina_gathers_in_recesses_and_grows_with_its_amount(bridge):
    results = {}
    for patina in (0.0, 0.35, 1.0):
        bridge.ok("new_scene")
        bridge.ok("material_procedural", name="Metal", brass={"patina": patina, "polish": 0.8})
        results[patina] = near_and_far(corner(bridge, "Metal"))
    assert results[0.0][0] >= 0.98 * results[0.0][1], results
    assert results[0.35][0] <= 0.6 * results[0.35][1], results
    assert results[0.35][1] >= 0.98 * results[0.0][1], results
    assert results[1.0][1] <= 0.6 * results[0.0][1], results


def test_polish_color_and_scratch_scale_set_the_look(bridge):
    for polish in (0.0, 0.5, 1.0):
        bridge.ok("new_scene")
        facing_plane(bridge, [0.0, 0.0, 0.0])
        bridge.ok("material_procedural", name="Metal", brass={"polish": polish, "patina": 0.0})
        mean = float(bake(bridge, "Metal", "Plate", ["roughness"])["roughness"][CROP:-CROP, CROP:-CROP, 0].mean())
        assert abs(mean - (0.06 + 0.4 * (1.0 - polish))) <= 0.03, (polish, mean)
    bridge.ok("new_scene")
    facing_plane(bridge, [0.0, 0.0, 0.0])
    brass_color = [0.5, 0.3, 0.1]
    bridge.ok("material_procedural", name="Metal", brass={"color": brass_color, "polish": 1.0, "patina": 0.0})
    mean = bake(bridge, "Metal", "Plate", ["base_color"])["base_color"][CROP:-CROP, CROP:-CROP, :3].mean(axis=(0, 1))
    for value, expected in zip(mean, brass_color):
        assert srgb(expected) - 0.01 <= value <= srgb(min(1.0, expected * 1.12)) + 0.01, (mean, brass_color)
    counts = []
    for scale in (0.25, 1.0):
        bridge.ok("material_procedural", name="Metal", brass={"polish": 0.0, "patina": 0.0, "scratch_scale": scale})
        rough = bake(bridge, "Metal", "Plate", ["roughness"])["roughness"][CROP:-CROP, CROP:-CROP, 0]
        raised = rough > 0.46 + 0.01
        across = ((raised[:, 1:] & ~raised[:, :-1]).sum(axis=1).mean(), (raised[1:, :] & ~raised[:-1, :]).sum(axis=0).mean())
        counts.append(float(max(across)))
    assert counts[0] >= 5.0 and counts[1] >= 2.5 * counts[0], counts


def test_brass_has_typed_parameters_and_refuses_bad_ones(bridge):
    assert "brass" in PRESETS and {"color", "patina_color", "patina", "polish", "scratch_scale", "scratch_direction"} <= set(PRESETS["brass"].properties)
    result = bridge.ok("material_procedural", name="Aged", brass={"patina": 0.6, "polish": 0.3, "scratch_direction": "around_y", "scratch_scale": 2.5, "seed": 4})
    assert result["preset"] == "brass" and result["params"]["scratch_direction"] == "around_y" and result["params"]["patina"] == 0.6
    bridge.ok("material_layer", material="Aged", brass={}, mask="noise", amount=0.4)
    before = world_state()
    for bad in ({"polish": 1.5}, {"patina": -0.1}, {"scratch_scale": 0.0}, {"color": [0.5, 0.5]}, {"patina_color": [0.1, 0.1, 0.1, 0.1]}, {"scratch_direction": "w"}, {"cracks": True}):
        bridge.refuse("material_procedural", "bad_args", name="Aged", brass=bad)
    for name in ("brass", "worn_metal"):
        message = bridge.refuse("material_procedural", "bad_args", name="Aged", **{name: {"scratch_direction": "z", "coordinates": "uv"}})
        assert "object coordinates" in message
    assert world_state() == before
    for name in ("brass", "worn_metal"):
        bridge.ok("material_procedural", name="Turned", **{name: {"scratch_direction": "around_z", "coordinates": "uv"}})
    bridge.ok("material_procedural", name="Planar", brass={"scratch_direction": "y", "coordinates": "uv"})


run(globals())
