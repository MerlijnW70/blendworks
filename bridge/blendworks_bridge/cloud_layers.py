"""Cloud layers: observer, resolution against the sky and light at a layer."""

import math

import bpy
import numpy as np

from . import cloud_genera, sky_measure, sky_sun, sky_world
from .errors import bad_args

FORMS = ("auto", "volume", "sheet")
DEFAULT_RADIUS = 15_000.0
STORM_DISTANCE = 38_000.0
STORM_SIDE = 15_000.0
SKY_VISIBILITY = 60_000.0
MIN_MU = {"heap": 0.12, "anvil": 0.12, "layer": 0.03, "fibres": 0.2}
OVERCAST_HORIZON = 1.6


def observer(scene, given):
    if given is not None:
        return [float(given[0]), float(given[1])]
    camera = scene.camera
    if camera is not None:
        location = camera.matrix_world.translation
        return [round(float(location.x), 3), round(float(location.y), 3)]
    return [0.0, 0.0]


def view_heading(scene):
    camera = scene.camera
    if camera is None:
        return (0.0, 1.0)
    forward = camera.matrix_world.to_3x3().col[2] * -1.0
    length = math.hypot(forward.x, forward.y)
    return (forward.x / length, forward.y / length) if length > 1e-6 else (0.0, 1.0)


def resolve(entry, index, scene, centre, radius):
    base = cloud_genera.genus(entry["genus"])
    layer = dict(base)
    layer["genus"] = entry["genus"]
    for key in ("coverage", "base", "thickness", "cell"):
        if key in entry:
            layer[key] = entry[key]
    layer["density"] = entry.get("density", 1.0)
    layer["seed"] = entry.get("seed", index)
    layer["wind_direction"] = entry.get("wind_direction", 90.0)
    layer["drift"] = entry.get("drift", 0.0)
    layer["brightness"] = entry.get("brightness", 1.0)
    layer["tint"] = list(entry.get("tint", [1.0, 1.0, 1.0]))
    layer["offset"] = [0.0, 0.0]
    layer["radius"] = radius
    layer["min_mu"] = MIN_MU["fibres" if layer["fibres"] > 0.0 else layer["profile"]]
    if layer["genus"] == "cumulonimbus":
        heading = view_heading(scene)
        left = (-heading[1], heading[0])
        ahead = [centre[0] + heading[0] * STORM_DISTANCE + left[0] * STORM_SIDE, centre[1] + heading[1] * STORM_DISTANCE + left[1] * STORM_SIDE]
        layer["centre"] = list(entry.get("centre", ahead))
        layer["anvil_radius"] = max(radius * math.sqrt(layer["coverage"]), layer["cell"] * 1.2)
        layer["tower_radius"] = layer["cell"]
        layer["threshold"] = 0.5
    else:
        if "centre" in entry:
            raise bad_args(f"layers[{index}].centre places a cumulonimbus; {layer['genus']} layers cover the sky")
        layer["threshold"] = cloud_genera.threshold(layer["coverage"])
    return layer


def native_sky(world):
    settings = sky_world.stored(world)
    if settings is None:
        raise bad_args("clouds need the procedural sky: call sky or weather first")
    return settings


def light_at(sky, height, cache):
    dip = math.degrees(math.sqrt(2.0 * height / 6_371_000.0))
    elevation = round(sky["elevation"] + dip, 3)
    if elevation in cache:
        return cache[elevation]
    world = bpy.data.worlds.new("blendworks cloud light")
    try:
        node = world.node_tree.nodes.new("ShaderNodeTexSky")
        settings = dict(sky)
        settings["elevation"] = min(elevation, 90.0)
        sky_world.node_settings(node, settings)
        found = sky_measure.measure(node, sky_sun.direction(settings["elevation"], sky["azimuth"]))
    finally:
        bpy.data.worlds.remove(world)
    cache[elevation] = {"sun": [float(value) for value in found["sun_rgb"]], "sky": [float(value) for value in found["sky_irradiance"]]}
    return cache[elevation]


def add_light(layers, sky):
    """Light reaching each layer: the sky's sun and sky light at its height, through the layers above it."""
    cache = {}
    for layer in layers:
        light = light_at(sky, layer["base"] + layer["thickness"] * 0.5, cache)
        above = [other for other in layers if other is not layer and other["base"] > layer["base"]]
        sun = sun_share(above)
        diffuse = diffuse_share(above)
        mu = max(math.sin(math.radians(sky["elevation"])), 0.0)
        scattered = [value * mu * (1.0 - sun) * diffuse for value in light["sun"]]
        layer["light"] = {
            "sun": [value * sun for value in light["sun"]],
            "sky": [value * diffuse + extra for value, extra in zip(light["sky"], scattered)],
        }


def cover_of(layers):
    clear = 1.0
    for layer in layers:
        clear *= 1.0 - min(layer["coverage"], 1.0) * min(1.0, layer["extinction"] * layer["density"] * layer["thickness"] / 3.0)
    return 1.0 - clear


def overcast_air(layers, sky):
    """Grey airlight under a deck: the mean base radiance of the thickest layer, in the sky's own units."""
    if not layers:
        return [0.0, 0.0, 0.0]
    thickest = max(layers, key=lambda layer: layer["extinction"] * layer["density"] * layer["thickness"] * layer["coverage"])
    light = thickest["light"]
    mu = max(math.sin(math.radians(sky["elevation"])), 0.0)
    depth = max(thickest["extinction"] * thickest["density"] * thickest["thickness"] * 0.5, 1.0)
    diffuse = 1.0 / (1.0 + 0.75 * 0.15 * depth)
    total = (np.asarray(light["sun"]) * mu + np.asarray(light["sky"])) * diffuse / math.pi
    grey = float(np.dot(total, sky_measure.LUMINANCE))
    tint = np.array([0.96, 0.99, 1.05]) * OVERCAST_HORIZON
    return [round(grey * float(value), 6) for value in tint]


def diffuse_share(layers):
    """Share of the clear-sky light that reaches the ground through the cover, two-stream estimate."""
    share = 1.0
    for layer in layers:
        depth = layer["extinction"] * layer["density"] * layer["thickness"] * 0.6
        through = 1.0 / (1.0 + 0.75 * 0.15 * depth)
        share *= 1.0 - layer["coverage"] * (1.0 - through)
    return share


def sun_share(layers):
    share = 1.0
    for layer in layers:
        depth = layer["extinction"] * layer["density"] * layer["thickness"] * 0.6
        share *= 1.0 - layer["coverage"] * (1.0 - math.exp(-depth))
    return share


def base_radiance(layers, sky):
    """Luminance of the lowest closed layer's base as the sheet shades it seen from below, in the sky's own units."""
    covering = [layer for layer in layers if layer["coverage"] >= 0.5] or layers
    lowest = min(covering, key=lambda layer: layer["base"])
    light = lowest["light"]
    mu = max(math.sin(math.radians(sky["elevation"])), 0.0)
    depth = lowest["extinction"] * lowest["density"] * lowest["thickness"] * 0.75
    diffuse = 1.0 / (1.0 + 0.75 * 0.15 * depth)
    total = (np.asarray(light["sun"]) * mu * diffuse + np.asarray(light["sky"]) * (diffuse + (1.0 - diffuse) * 0.075)) / math.pi
    tint = np.asarray(lowest["tint"]) * lowest["brightness"]
    return float(np.dot(total * tint, sky_measure.LUMINANCE))
