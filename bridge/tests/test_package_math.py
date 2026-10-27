import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package"))

import bmesh
import bpy
import numpy as np

from harness import close, run
from package_locks import feature_counts
from package_metrics import BACKGROUND, C1, compare_renders, covered_box, luminance, mean_ssim, silhouette_iou
from package_plan import allowed_error_metres, crop_angle, crop_pixels, level_plan, pixels_per_metre_at_one_metre, projected_pixels, reached, screen_error_pixels, switch_distance

SCALE = 540 / math.tan(math.radians(30))


def grid_mesh(cells=4):
    mesh = bpy.data.meshes.new("Grid")
    builder = bmesh.new()
    bmesh.ops.create_grid(builder, x_segments=cells, y_segments=cells, size=1.0)
    layer = builder.loops.layers.uv.new("UVMap")
    for face in builder.faces:
        for loop in face.loops:
            loop[layer].uv = ((loop.vert.co.x + 1) / 2, (loop.vert.co.y + 1) / 2)
    builder.to_mesh(mesh)
    builder.free()
    return mesh


def test_reference_display_scale(bridge):
    close(pixels_per_metre_at_one_metre(), SCALE, 1e-9)
    close(screen_error_pixels(0.01, 10.0), 0.01 * SCALE / 10.0, 1e-9)
    close(allowed_error_metres(1.0, 10.0), 10.0 / SCALE, 1e-12)
    close(screen_error_pixels(allowed_error_metres(2.5, 7.0), 7.0), 2.5, 1e-9)


def test_switch_distance_and_crop(bridge):
    close(switch_distance(0.01, 0.5), 0.01 * SCALE, 1e-9)
    close(switch_distance(1e-9, 0.5), 1.0, 1e-12)
    close(switch_distance(0.0001, 0.5, previous=4.0), 4.0, 1e-12)
    assert crop_pixels(100.0) == 128
    assert crop_pixels(300.0) == 384
    assert crop_pixels(2000.0) == 512
    close(projected_pixels(2.0, 10.0), 2.0 * SCALE / 10.0, 1e-9)
    close(crop_angle(256), 2 * math.atan(128 / SCALE), 1e-12)


def test_level_plan_modes(bridge):
    plan = level_plan({"count": 2, "ratios": [0.5, 0.25]})
    assert [entry["ratio"] for entry in plan] == [0.5, 0.25]
    assert all(entry["budget"] is None and entry["distance"] is None for entry in plan)
    screen = level_plan({"count": 2, "maxScreenError": 2.0, "distances": [10.0, 20.0]})
    close(screen[0]["budget"], 2.0 * 10.0 / SCALE, 1e-12)
    close(screen[1]["budget"], 2.0 * 20.0 / SCALE, 1e-12)
    assert level_plan({"count": 0}) == []
    for bad in ({"count": 1}, {"count": 2, "ratios": [0.5]}, {"count": 1, "maxScreenError": 1.0}, {"count": 9, "ratios": [0.5] * 9}, {"count": 1, "ratios": [0.5], "maxScreenError": 1.0, "distances": [5.0]}):
        try:
            level_plan(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} should be refused")


def test_reach_tolerance(bridge):
    assert reached(0.26, 0.25)
    assert not reached(0.27, 0.25)


def test_silhouette_iou_by_hand(bridge):
    first = np.zeros((4, 4), dtype=bool)
    second = np.zeros((4, 4), dtype=bool)
    first[:, :2] = True
    second[:, :3] = True
    close(silhouette_iou(first, second), 8 / 12, 1e-12)
    close(silhouette_iou(first, first), 1.0, 1e-12)
    close(silhouette_iou(np.zeros((4, 4), dtype=bool), np.zeros((4, 4), dtype=bool)), 1.0, 1e-12)
    close(silhouette_iou(first, ~first), 0.0, 1e-12)


def constant(value, size=16):
    image = np.zeros((size, size, 4))
    image[..., :3] = value
    image[..., 3] = 1.0
    return image


def test_ssim_by_hand(bridge):
    flat = np.full((16, 16), 0.5)
    close(mean_ssim(flat, flat), 1.0, 1e-12)
    darker = np.full((16, 16), 0.25)
    expected = (2 * 0.5 * 0.25 + C1) / (0.5**2 + 0.25**2 + C1)
    close(mean_ssim(flat, darker), expected, 1e-12)
    close(expected, 0.2501 / 0.3126, 1e-9)
    ramp = np.tile(np.linspace(0, 1, 16), (16, 1))
    close(mean_ssim(ramp, ramp), 1.0, 1e-12)
    assert mean_ssim(ramp, ramp[::-1, ::-1]) < 0.5


def test_luminance_composites_over_the_background(bridge):
    clear = np.zeros((2, 2, 4))
    assert np.allclose(luminance(clear), BACKGROUND, atol=1e-12)
    white = constant(1.0, 2)
    assert np.allclose(luminance(white), 1.0, atol=1e-12)


def test_compare_renders_reports_both_metrics(bridge):
    reference = np.zeros((32, 32, 4))
    reference[8:24, 8:24] = (0.8, 0.8, 0.8, 1.0)
    shifted = np.zeros((32, 32, 4))
    shifted[8:24, 12:28] = (0.8, 0.8, 0.8, 1.0)
    result = compare_renders(reference, shifted)
    close(result["silhouetteIou"], (16 * 12) / (16 * 20), 1e-12)
    assert 0.0 < result["similarity"] < 1.0
    assert result["silhouettePixels"] == [256, 256]
    same = compare_renders(reference, reference)
    close(same["silhouetteIou"], 1.0, 1e-12)
    close(same["similarity"], 1.0, 1e-12)
    empty = compare_renders(np.zeros((8, 8, 4)), np.zeros((8, 8, 4)))
    assert empty["silhouetteIou"] == 1.0 and empty["similarity"] == 1.0


def test_covered_box_pads_and_clips(bridge):
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:8, 10:12] = True
    assert covered_box(mask, 3, mask.shape) == (2, 11, 7, 15)
    assert covered_box(mask, 30, mask.shape) == (0, 20, 0, 20)
    assert covered_box(np.zeros((4, 4), dtype=bool), 3, (4, 4)) is None


def test_feature_vertices_of_an_open_grid(bridge):
    mesh = grid_mesh(4)
    counts = feature_counts(mesh)
    assert counts == {"border": 16, "material": 0, "seam": 0}


def test_material_boundary_and_uv_tear_are_found(bridge):
    mesh = grid_mesh(4)
    for _ in range(2):
        mesh.materials.append(bpy.data.materials.new("m"))
    for polygon in mesh.polygons:
        polygon.material_index = 1 if polygon.center.x > 0 else 0
    layer = mesh.uv_layers.active
    for polygon in mesh.polygons:
        if polygon.center.y > 0:
            for index in polygon.loop_indices:
                layer.uv[index].vector = (layer.uv[index].vector.x + 0.25, layer.uv[index].vector.y)
    counts = feature_counts(mesh)
    assert counts["material"] == 5
    assert counts["seam"] == 5


run(globals())
