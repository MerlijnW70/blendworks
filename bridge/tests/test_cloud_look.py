import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run
from sky_helpers import luminance, render

WIDTH = 3000.0
HEIGHT = 900.0
PIXELS = (300, 90)
LAYER = {"genus": "cumulus", "coverage": 0.35, "base": 1200.0, "thickness": 500.0, "cell": 700.0, "seed": 6}
EDGE_SHARE = 0.27
THIN_SHARE = 0.1
BETWEEN_LOW = 0.15
BETWEEN_HIGH = 0.85
FACE_FACTOR = 1.5
RIM_FACTOR = 3.0


def side_view(bridge, sun, dark=True, slab=True, depth=120.0):
    """An orthographic camera looking north at the clouds; with slab, clip planes keep only a slab of them depth metres deep."""
    bridge.ok("sky", sun=sun, exposure="keep")
    distance = 2000.0 if slab else 5000.0
    bridge.ok("add_camera", name="Side", location=[0.0, -distance, 1050.0 + HEIGHT / 2.0], rotation=[90.0, 0.0, 0.0], orthographic_scale=WIDTH)
    data = bpy.data.objects["Side"].data
    data.clip_start = distance - depth / 2.0 if slab else 1.0
    data.clip_end = distance + depth / 2.0 if slab else 20_000.0
    layer = LAYER if slab else dict(LAYER, coverage=0.1)
    bridge.ok("clouds", layers=[layer], form="volume", radius=3000.0, bounces=4)
    if dark:
        bpy.context.scene.world.node_tree.nodes["Sky Background"].inputs["Strength"].default_value = 0.0


def side(bridge, name, alpha=False):
    return render(bridge, name, PIXELS[0], 8, "Side", PIXELS[1], alpha)


def runs(mask):
    """Opaque runs along each row: (row, first column, last column)."""
    found = []
    for row in range(mask.shape[0]):
        columns = np.nonzero(mask[row])[0]
        if columns.size == 0:
            continue
        breaks = np.nonzero(np.diff(columns) > 1)[0]
        starts = np.concatenate([[columns[0]], columns[breaks + 1]])
        ends = np.concatenate([columns[breaks], [columns[-1]]])
        found.extend((row, start, end) for start, end in zip(starts, ends) if end - start >= 8)
    return found


def test_cloud_margins_fade_softly(bridge):
    """Through a slab 20 m deep the opacity follows the density: a hard cut gives only clear and full pixels."""
    side_view(bridge, {"elevation": 50.0, "azimuth": 180.0}, depth=20.0)
    alpha = side(bridge, "margins", alpha=True)[..., 3]
    cloud = alpha > 0.02
    full = float(np.percentile(alpha[cloud], 90))
    partial = cloud & (alpha < 0.5 * full)
    assert cloud.sum() > 300, cloud.sum()
    assert partial.sum() / cloud.sum() >= EDGE_SHARE, partial.sum() / cloud.sum()


def blueness(pixels):
    return pixels[..., 2] / np.maximum(pixels.sum(axis=-1), 1e-9)


def test_thin_cloud_shows_the_sky_through_it(bridge):
    bridge.ok("sky", sun={"elevation": 30.0, "azimuth": 180.0}, exposure="keep")
    bridge.ok("add_camera", name="Under", location=[0.0, 0.0, 1.0], rotation=[0.0, 180.0, 0.0], lens=20.0)
    bpy.data.objects["Under"].data.clip_end = 100_000.0
    clear = blueness(render(bridge, "clear", 96, 16, "Under"))
    bridge.ok("clouds", layers=[LAYER], form="volume", radius=3000.0, bounces=4)
    cloudy = blueness(render(bridge, "cloudy", 96, 16, "Under"))
    alpha = render(bridge, "cloudy_alpha", 96, 16, "Under", alpha=True)[..., 3]
    cloud = alpha > 0.05
    thin = (alpha > 0.15) & (alpha < 0.85)
    core = alpha > 0.97
    assert core.sum() > 50 and thin.sum() / cloud.sum() >= THIN_SHARE, (core.sum(), thin.sum() / cloud.sum())
    core_blue = float(np.median(cloudy[core]))
    sky_blue = float(np.median(clear[thin]))
    thin_blue = float(np.median(cloudy[thin]))
    assert core_blue < thin_blue < sky_blue, (core_blue, thin_blue, sky_blue)
    share = (thin_blue - core_blue) / (sky_blue - core_blue)
    assert BETWEEN_LOW <= share <= BETWEEN_HIGH, share


def test_sunlit_faces_are_brighter_than_the_shaded_core(bridge):
    side_view(bridge, {"elevation": 12.0, "azimuth": 90.0}, slab=False)
    pixels = side(bridge, "faces", alpha=True)
    light = luminance(pixels[..., :3])
    faces, cores = [], []
    for row, start, end in runs(pixels[..., 3] > 0.9):
        faces.append(light[row, end - 3 : end + 1].max())
        middle = (start + end) // 2
        cores.append(light[row, middle - 1 : middle + 2].mean())
    assert len(faces) >= 10, len(faces)
    assert float(np.mean(faces)) >= FACE_FACTOR * float(np.mean(cores)), (np.mean(faces), np.mean(cores))


def test_silver_lining_when_the_sun_is_behind(bridge):
    side_view(bridge, {"elevation": 5.0, "azimuth": 0.0}, slab=False)
    pixels = side(bridge, "lining", alpha=True)
    alpha = pixels[..., 3]
    light = luminance(pixels[..., :3]) / np.maximum(alpha, 1e-6)
    rim = (alpha > 0.1) & (alpha < 0.6)
    core = alpha > 0.97
    assert rim.sum() > 30 and core.sum() > 30, (rim.sum(), core.sum())
    assert float(light[rim].mean()) >= RIM_FACTOR * float(light[core].mean()), (light[rim].mean(), light[core].mean())


run(globals())
