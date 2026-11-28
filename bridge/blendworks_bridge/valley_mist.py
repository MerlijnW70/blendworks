"""Mist that lies in low ground. The ground under a square around a centre is measured on a grid by ray casts; the low
ground is the lowest ground within a valley width of each cell, smoothed over the same width, so it runs along valley
floors and over water as they rise and fall. Where the ground lies below the mean of its surroundings the mist's top lies
a thickness above the low ground; on ridges and plateaus it sinks to the ground; its density is full
below the top, fades over a soft top and is broken up by a seeded noise. The top heights are a float image the volume
shader reads by world x and y, so the mist follows the land wherever it sits in z.

When it forms: valley (radiation) mist forms in the night and early morning under a clear sky, in light wind and moist
air, in low ground; it lifts and burns off as the sun warms the ground. The rules and their sources:
- light wind: radiation fog is unlikely above 8 knots (4.1 m/s) at 10 m (US National Weather Service fog training guide;
  Kadioglu, ITU fog lecture notes);
- moist air: mist is reported only in air near saturation, relative humidity from 95 % (WMO, International
  Meteorological Vocabulary, mist versus haze);
- clear sky: radiative cooling of the ground needs a sky at most half covered (4 oktas);
- early morning: the sun below the horizon or rising (azimuth east of the meridian) and not yet past the burn-off height;
- thickness: from WMO's shallow fog (under 2 m) to the about 50 m of shallow radiation fog (Steeneveld et al. 2015,
  fog-top height), default the geometric centre, 10 m; density: visibility inside the mist of 1 to 5 km (WMO mist),
  default the geometric centre, 2.24 km;
- burn-off: shallow radiation fog turns deep and lifts about 2 hours after it thickens and is gone some 3 hours after
  sunrise (Smith 2020, UEA, the 2014 LANFEX case); 3 hours after sunrise at 50 degrees north at the equinox the sun stands
  asin(cos 50 sin 45) = 27.0 degrees high. With b = the sun's height over that, clipped to 0..1, the mist's density is
  (1 - b) times full and the whole layer lifts by b times its thickness: it thins and rises off the ground."""
import math

import bpy
import numpy

from .atmosphere_haze import extinction

FLAG = "blendworks_valley_mist"
PROPERTY = "blendworks_valley_mist_settings"
TOP_IMAGE_SUFFIX = "_top"
BREAKUP_WAVELENGTH = 180.0
WIND_LIMIT = 8.0 * 0.514444
HUMIDITY_LIMIT = 0.95
COVER_LIMIT = 0.5
THICKNESS_RANGE = (2.0, 50.0)
VISIBILITY_RANGE = (1000.0, 5000.0)
DEFAULT_THICKNESS = math.sqrt(THICKNESS_RANGE[0] * THICKNESS_RANGE[1])
DEFAULT_VISIBILITY = math.sqrt(VISIBILITY_RANGE[0] * VISIBILITY_RANGE[1])
BURN_OFF_LATITUDE = 50.0
BURN_OFF_HOURS = 3.0
BURN_OFF_ELEVATION = math.degrees(math.asin(math.cos(math.radians(BURN_OFF_LATITUDE)) * math.sin(math.radians(15.0 * BURN_OFF_HOURS))))
DAWN = {"sun_elevation": 0.0, "sun_azimuth": 90.0, "wind": 1.0, "humidity": 0.97, "cover": 0.0}


def burn_off(elevation):
    """Share of the mist the sun has burnt off at a sun height: 0 at sunrise and before, 1 from the burn-off height."""
    return min(max(elevation / BURN_OFF_ELEVATION, 0.0), 1.0)


def formation(conditions):
    """Whether mist lies in the low ground under these conditions, why not, and how far the sun has burnt it off."""
    reasons = []
    if conditions["wind"] > WIND_LIMIT:
        reasons.append(f"wind {conditions['wind']:g} m/s is above the {WIND_LIMIT:.1f} m/s radiation mist needs")
    if conditions["humidity"] < HUMIDITY_LIMIT:
        reasons.append(f"relative humidity {conditions['humidity']:g} is below {HUMIDITY_LIMIT:g}")
    if conditions["cover"] > COVER_LIMIT:
        reasons.append(f"cloud cover {conditions['cover']:g} keeps the ground from cooling (more than {COVER_LIMIT:g})")
    elevation = conditions["sun_elevation"]
    rising = 0.0 <= conditions["sun_azimuth"] % 360.0 <= 180.0
    if elevation > 0.0 and not rising:
        reasons.append("the sun is past noon: mist forms in the night and the early morning")
    burnt = burn_off(elevation) if rising or elevation <= 0.0 else 1.0
    if burnt >= 1.0 and not reasons:
        reasons.append(f"the sun is {elevation:g} degrees high, past the burn-off height of {BURN_OFF_ELEVATION:.1f}")
    return {"forms": not reasons, "because": reasons, "burnt": round(burnt, 6), "density": round(0.0 if reasons else 1.0 - burnt, 6)}


def sliding_minimum(values, radius):
    """Minimum over a square window of (2 radius + 1) cells, edges repeated, by separable passes."""
    result = values
    for axis in (0, 1):
        padded = numpy.pad(result, [(radius, radius) if a == axis else (0, 0) for a in (0, 1)], mode="edge")
        stacked = numpy.lib.stride_tricks.sliding_window_view(padded, 2 * radius + 1, axis=axis)
        result = stacked.min(axis=-1)
    return result


def box_blur(values, radius):
    result = values
    for axis in (0, 1):
        padded = numpy.pad(result, [(radius, radius) if a == axis else (0, 0) for a in (0, 1)], mode="edge")
        stacked = numpy.lib.stride_tricks.sliding_window_view(padded, 2 * radius + 1, axis=axis)
        result = stacked.mean(axis=-1)
    return result


def low_ground(ground, cell, valley_width):
    radius = max(1, int(round(valley_width / (2.0 * cell))))
    lowest = sliding_minimum(ground, radius)
    return box_blur(box_blur(lowest, radius), radius)


def lowness(ground, cell, valley_width):
    """How far the ground lies below the mean of its surroundings, four valley widths across: positive in valleys and
    hollows, negative on ridges and plateaus (the topographic position index, negated)."""
    radius = max(1, int(round(2.0 * valley_width / cell)))
    return box_blur(ground, radius) - ground


def mist_top(ground, cell, valley_width, thickness):
    """Top of the mist: the low ground plus the thickness where the land is low, falling to the ground on high land."""
    floor = low_ground(ground, cell, valley_width)
    share = numpy.clip(lowness(ground, cell, valley_width) / max(thickness, 1e-6) + 0.5, 0.0, 1.0)
    share = share * share * (3.0 - 2.0 * share)
    return numpy.minimum(floor, ground) + thickness * share, floor


def bilinear(grid, low, size, xy):
    """Values of a cell-centred grid at points, as Cycles' linear image lookup reads them, edges extended."""
    rows, columns = grid.shape
    u = (xy[:, 0] - low[0]) / size[0] * columns - 0.5
    v = (xy[:, 1] - low[1]) / size[1] * rows - 0.5
    u = numpy.clip(u, 0.0, columns - 1.0)
    v = numpy.clip(v, 0.0, rows - 1.0)
    i0 = numpy.floor(u).astype(int)
    j0 = numpy.floor(v).astype(int)
    i1 = numpy.minimum(i0 + 1, columns - 1)
    j1 = numpy.minimum(j0 + 1, rows - 1)
    fu, fv = u - i0, v - j0
    return ((grid[j0, i0] * (1 - fu) + grid[j0, i1] * fu) * (1 - fv) + (grid[j1, i0] * (1 - fu) + grid[j1, i1] * fu) * fv)


def lifted(top, floor, ground, thickness, burnt):
    """Top and base of the mist after the sun has lifted it by burnt times its thickness."""
    lift = burnt * thickness
    return top + lift, numpy.minimum(floor, ground) + lift


def density(settings, grid, xy, z):
    """Mist extinction per metre at points, without the breakup noise: full between base and top, fading over the fade
    above the top and below a lifted base. grid holds the top, or the top and base as its last axis."""
    grid = numpy.asarray(grid)
    top = bilinear(grid[..., 0] if grid.ndim == 3 else grid, settings["low"], settings["size"], xy)
    share = numpy.clip((top - z) / settings["fade"], 0.0, 1.0)
    if grid.ndim == 3:
        base = bilinear(grid[..., 1], settings["low"], settings["size"], xy)
        share = share * numpy.clip((z - base) / settings["fade"] + 1.0, 0.0, 1.0)
    return extinction(settings["visibility"]) * settings.get("density", 1.0) * share


def top_image(name, top, base):
    """Red holds the top, green the base."""
    rows, columns = top.shape
    image = bpy.data.images.new(name, columns, rows, alpha=False, float_buffer=True, is_data=True)
    pixels = numpy.zeros((rows, columns, 4), dtype=numpy.float32)
    pixels[..., 0] = top
    pixels[..., 1] = base
    pixels[..., 2] = top
    pixels[..., 3] = 1.0
    image.pixels.foreach_set(pixels.ravel())
    image.file_format = "OPEN_EXR"
    image.pack()
    return image


def node(tree, kind, location, **inputs):
    made = tree.nodes.new(kind)
    made.location = location
    for key, value in inputs.items():
        made.inputs[key].default_value = value
    return made


def mist_material(name, image, settings):
    material = bpy.data.materials.new(name)
    tree = material.node_tree
    tree.nodes.clear()
    links = tree.links
    output = node(tree, "ShaderNodeOutputMaterial", (600, 0))
    scatter = node(tree, "ShaderNodeVolumeScatter", (400, 0))
    scatter.inputs["Color"].default_value = list(settings["tint"]) + [1.0]
    scatter.inputs["Anisotropy"].default_value = settings["anisotropy"]
    geometry = node(tree, "ShaderNodeNewGeometry", (-1400, 0))
    mapping = node(tree, "ShaderNodeMapping", (-1200, 0))
    mapping.vector_type = "POINT"
    mapping.inputs["Location"].default_value = (-settings["low"][0] / settings["size"][0], -settings["low"][1] / settings["size"][1], 0.0)
    mapping.inputs["Scale"].default_value = (1.0 / settings["size"][0], 1.0 / settings["size"][1], 1.0)
    links.new(geometry.outputs["Position"], mapping.inputs["Vector"])
    texture = node(tree, "ShaderNodeTexImage", (-1000, 0))
    texture.image = image
    texture.interpolation = "Linear"
    texture.extension = "EXTEND"
    links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    separate = node(tree, "ShaderNodeSeparateXYZ", (-1000, -300))
    links.new(geometry.outputs["Position"], separate.inputs[0])
    heights = node(tree, "ShaderNodeSeparateColor", (-850, 150))
    links.new(texture.outputs["Color"], heights.inputs["Color"])
    gap = node(tree, "ShaderNodeMath", (-800, 0))
    gap.operation = "SUBTRACT"
    links.new(heights.outputs[0], gap.inputs[0])
    links.new(separate.outputs["Z"], gap.inputs[1])
    upper = node(tree, "ShaderNodeMath", (-650, 0))
    upper.operation = "DIVIDE"
    upper.use_clamp = True
    upper.inputs[1].default_value = settings["fade"]
    links.new(gap.outputs[0], upper.inputs[0])
    rise = node(tree, "ShaderNodeMath", (-800, 200))
    rise.operation = "SUBTRACT"
    links.new(separate.outputs["Z"], rise.inputs[0])
    links.new(heights.outputs[1], rise.inputs[1])
    lower = node(tree, "ShaderNodeMath", (-650, 200))
    lower.operation = "MULTIPLY_ADD"
    lower.use_clamp = True
    lower.inputs[1].default_value = 1.0 / settings["fade"]
    lower.inputs[2].default_value = 1.0
    links.new(rise.outputs[0], lower.inputs[0])
    share = node(tree, "ShaderNodeMath", (-550, 0))
    share.operation = "MULTIPLY"
    links.new(upper.outputs[0], share.inputs[0])
    links.new(lower.outputs[0], share.inputs[1])
    noise = node(tree, "ShaderNodeTexNoise", (-800, -400))
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = 1.0 / BREAKUP_WAVELENGTH
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["W"].default_value = settings["seed"] * 7.31
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    breakup = node(tree, "ShaderNodeMapRange", (-600, -400))
    breakup.inputs["From Min"].default_value = 0.3
    breakup.inputs["From Max"].default_value = 0.7
    breakup.inputs["To Min"].default_value = 1.0 - settings["breakup"]
    breakup.inputs["To Max"].default_value = 1.0
    links.new(noise.outputs[0], breakup.inputs["Value"])
    weighted = node(tree, "ShaderNodeMath", (-400, 0))
    weighted.operation = "MULTIPLY"
    links.new(share.outputs[0], weighted.inputs[0])
    links.new(breakup.outputs[0], weighted.inputs[1])
    scaled = node(tree, "ShaderNodeMath", (-200, 0))
    scaled.operation = "MULTIPLY"
    scaled.inputs[1].default_value = extinction(settings["visibility"]) * settings.get("density", 1.0)
    links.new(weighted.outputs[0], scaled.inputs[0])
    links.new(scaled.outputs[0], scatter.inputs["Density"])
    links.new(scatter.outputs[0], output.inputs["Volume"])
    return material


def coverage(ground, top):
    return float((top > ground).mean())

