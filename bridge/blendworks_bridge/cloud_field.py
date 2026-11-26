import math

from . import cloud_genera

FOOTPRINT_DETAIL = 2.0
FOOTPRINT_ROUGHNESS = 0.5
BREAKUP_FREQUENCY = 3.1
BREAKUP_WEIGHT = 0.35
SEED_STEP = (7.31, 3.77, 11.13)
SEED_WRAP = 97.0
SIDE_SCALE = 3.0
ANVIL_LENGTH = 1.7
BASE_METRES = 60.0
BASE_GRAIN = 140.0
BASE_STEEPNESS = 3.0
FRAY_SCALE = 0.06
FRAY_STORM = 0.12
MARGIN = 6.0
MARGIN_METRES = 160.0
STORM_MARGIN_METRES = 450.0
ANVIL_LOW = 0.8


def seed_offset(seed):
    return tuple(((seed + 1) * step) % SEED_WRAP + 13.0 for step in SEED_STEP)


def wind_frame(layer):
    angle = math.radians(layer["wind_direction"])
    along = (math.sin(angle), math.cos(angle))
    return along, (along[1], -along[0])


def layer_coordinates(graph, x, y, layer):
    """Horizontal position in the layer's frame: drifted along the wind, stretched along it, in cells."""
    along, across = wind_frame(layer)
    drift = layer["drift"]
    shifted_x = graph.sub(x, along[0] * drift + layer["offset"][0])
    shifted_y = graph.sub(y, along[1] * drift + layer["offset"][1])
    cell = layer["cell"]
    u = graph.add(graph.mul(shifted_x, along[0] / (cell * layer["elongation"])), graph.mul(shifted_y, along[1] / (cell * layer["elongation"])))
    v = graph.add(graph.mul(shifted_x, across[0] / cell), graph.mul(shifted_y, across[1] / cell))
    return u, v


def footprint(graph, u, v, seed):
    """The 2D field whose quantiles cloud_genera.QUANTILES tabulates: broad noise plus a finer break-up."""
    offset = seed_offset(seed)
    broad = graph.noise(graph.combine(graph.add(u, offset[0]), graph.add(v, offset[1]), offset[2]), 1.0, FOOTPRINT_DETAIL, FOOTPRINT_ROUGHNESS)
    fine_vector = graph.combine(graph.add(graph.mul(u, BREAKUP_FREQUENCY), offset[1]), graph.add(graph.mul(v, BREAKUP_FREQUENCY), offset[2]), offset[0])
    fine = graph.noise(fine_vector, 1.0, FOOTPRINT_DETAIL, FOOTPRINT_ROUGHNESS)
    return graph.madd(graph.sub(fine, 0.5), BREAKUP_WEIGHT, broad)


def span_of(threshold):
    return max(cloud_genera.QUANTILES[-1] - threshold, 0.04)


def column_share(graph, excess, layer):
    """Share of the layer thickness the cloud fills above a point: a dome for heaps and anvils, a slab for layers."""
    span = span_of(layer["threshold"])
    share = graph.clamp01(graph.div(excess, span))
    rounded = graph.power(share, layer["roundness"])
    if layer["flat_top"] <= 0.0:
        return rounded
    return graph.mix_value(layer["flat_top"], rounded, graph.smooth(0.0, 0.15, share))


def base_offset(graph, position, u, v, excess, layer):
    """Height above a ragged underside, in thicknesses: each cloud's base sits a little higher or lower,
    sags in its middle, and frays into wisps that hang below it."""
    x, y, z = graph.separate(position)
    height = graph.div(graph.sub(z, layer["base"]), layer["thickness"])
    metres = BASE_METRES / layer["thickness"]
    offset = seed_offset(layer["seed"] + 41)
    per_cloud = graph.noise(graph.combine(graph.add(graph.mul(u, 0.7), offset[0]), graph.add(graph.mul(v, 0.7), offset[1]), offset[2]), 1.0, 1.0, 0.5)
    ragged = graph.noise(graph.vector("ADD", graph.vector("SCALE", position, None, 1.0 / BASE_GRAIN), offset), 1.0, 4.0, 0.6)
    sag = graph.mul(graph.clamp01(graph.div(excess, span_of(layer["threshold"]))), metres * 0.9)
    shift = graph.add(graph.remap(per_cloud, 0.3, 0.7, -metres * 1.3, metres * 1.3, False), sag)
    shift = graph.add(graph.remap(ragged, 0.3, 0.7, -metres * 0.8, metres * 0.8, False), shift)
    return graph.add(height, shift)


def towers(graph, u, v, layer):
    """Heaps differ in height from cell to cell: a slow noise scales the top between 0.45 and 1.3."""
    if layer["profile"] != "heap":
        return 1.0
    offset = seed_offset(layer["seed"] + 29)
    slow = graph.noise(graph.combine(graph.add(graph.mul(u, 0.45), offset[0]), graph.add(graph.mul(v, 0.45), offset[1]), offset[2]), 1.0, 1.0, 0.5)
    return graph.remap(slow, 0.3, 0.7, 0.45, 1.3)


def rolls(graph, u, v, layer):
    """Lumpy undersides of a deck: thicker rolls and thinner gaps at a third of the cell size."""
    offset = seed_offset(layer["seed"] + 37)
    lumps = graph.noise(graph.combine(graph.add(graph.mul(u, 3.5), offset[0]), graph.add(graph.mul(v, 5.0), offset[1]), offset[2]), 1.0, 3.0, 0.55)
    return graph.remap(lumps, 0.3, 0.7, 0.35, 1.5)


def fibres(graph, u, v, z, layer):
    offset = seed_offset(layer["seed"] + 5)
    streak = graph.noise(graph.combine(graph.add(graph.mul(u, 1.5), offset[0]), graph.add(graph.mul(v, 4.0), offset[1]), graph.add(graph.mul(z, 0.002), offset[2])), 1.0, 4.0, 0.6)
    return graph.mix_value(layer["fibres"], 1.0, graph.smooth(0.35, 0.75, streak))


def bubble(graph, point, scale):
    distance = graph.voronoi(point, scale)
    cap = graph.math("SQRT", graph.maximum(graph.madd(graph.mul(distance, distance), -1.0 / 0.55, 1.0), 0.0))
    return graph.sub(cap, 0.45)


def billows(graph, position, layer):
    """Round turrets: two octaves of spherical caps on Voronoi cells, warped by a smooth noise."""
    offset = seed_offset(layer["seed"] + 11)
    size = layer["cell"] * layer["billow_scale"]
    point = graph.vector("ADD", graph.vector("SCALE", position, None, 1.0 / size), offset)
    warp = graph.noise(point, 0.5, 2.0, 0.5)
    point = graph.vector("ADD", point, graph.combine(warp, graph.mul(warp, -0.7), graph.mul(warp, 0.4)))
    coarse = bubble(graph, point, 1.0)
    if layer["detail"] <= 0.0:
        return coarse
    return graph.madd(bubble(graph, point, 2.9), layer["detail"], coarse)


def density(graph, position, layer):
    """Extinction per metre at a world position, for the volume form: flat base, dome or slab top, round turrets."""
    x, y, z = graph.separate(position)
    u, v = layer_coordinates(graph, x, y, layer)
    field = footprint(graph, u, v, layer["seed"])
    excess = graph.sub(field, layer["threshold"])
    height = graph.div(graph.sub(z, layer["base"]), layer["thickness"])
    underside = graph.mul(base_offset(graph, position, u, v, excess, layer), BASE_STEEPNESS)
    if layer["genus"] == "cumulonimbus":
        shape = graph.minimum(anvil_excess(graph, x, y, z, layer), underside)
    else:
        top = graph.mul(column_share(graph, excess, layer), towers(graph, u, v, layer))
        side = graph.mul(graph.div(excess, span_of(layer["threshold"])), SIDE_SCALE)
        shape = graph.minimum(graph.minimum(graph.sub(top, height), underside), side)
    lift = graph.smooth(0.0, 0.2, height)
    if layer["genus"] == "cumulonimbus":
        lift = graph.mul(lift, graph.sub(1.0, graph.smooth(ANVIL_LOW - 0.08, ANVIL_LOW + 0.02, height)))
    shape = graph.add(shape, graph.mul(billows(graph, position, layer), graph.mul(lift, layer["billow"])))
    fill = vapour(graph, position, shape, layer)
    if layer["genus"] == "cumulonimbus":
        fill = graph.mul(fill, anvil_streaks(graph, u, v, height, layer))
    if layer["fibres"] > 0.0:
        fill = graph.mul(fill, fibres(graph, u, v, z, layer))
    return graph.mul(fill, layer["extinction"] * layer["density"])


def anvil_streaks(graph, u, v, height, layer):
    """The anvil is ice: smooth, streaked along the wind and frayed at its far end."""
    offset = seed_offset(layer["seed"] + 53)
    streak = graph.noise(graph.combine(graph.add(graph.mul(u, 0.4), offset[0]), graph.add(graph.mul(v, 6.0), offset[1]), graph.add(graph.mul(height, 3.0), offset[2])), 1.0, 4.0, 0.6)
    anvil = graph.smooth(ANVIL_LOW - 0.05, ANVIL_LOW + 0.03, height)
    return graph.mix_value(anvil, 1.0, graph.remap(streak, 0.3, 0.7, 0.25, 1.2))


def vapour(graph, position, shape, layer):
    """Density from the shape: a soft margin that small noise frays into wisps, and denser and thinner parcels inside."""
    offset = seed_offset(layer["seed"] + 47)
    scale = FRAY_STORM if layer["genus"] == "cumulonimbus" else FRAY_SCALE
    point = graph.vector("ADD", graph.vector("SCALE", position, None, 1.0 / (layer["cell"] * scale)), offset)
    fray = graph.remap(graph.noise(point, 1.0, 4.0, 0.6), 0.3, 0.7, -1.0, 1.0, False)
    if layer["genus"] == "cumulonimbus":
        soft = STORM_MARGIN_METRES * 0.25 / layer["tower_radius"]
    else:
        soft = min(layer["edge"] * MARGIN, MARGIN_METRES / layer["thickness"])
    margin = graph.smooth(0.0, soft, graph.madd(fray, soft * 0.6, shape))
    parcels = graph.remap(graph.noise(graph.vector("SCALE", point, None, 0.35), 1.0, 3.0, 0.5), 0.3, 0.7, 0.45, 1.15)
    return graph.mul(graph.power(margin, 1.6), parcels)


def anvil_excess(graph, x, y, z, layer):
    """A storm cell: a lumpy tower from the base to the top, joined to an anvil that fans out downwind under the top."""
    centre = layer["centre"]
    tower = layer["tower_radius"]
    length = layer["anvil_radius"] * ANVIL_LENGTH
    thickness = layer["thickness"]
    along, across = wind_frame(layer)
    dx = graph.sub(x, centre[0])
    dy = graph.sub(y, centre[1])
    downwind = graph.add(graph.mul(dx, along[0]), graph.mul(dy, along[1]))
    sideways = graph.math("ABSOLUTE", graph.add(graph.mul(dx, across[0]), graph.mul(dy, across[1])))
    distance = graph.math("SQRT", graph.add(graph.mul(dx, dx), graph.mul(dy, dy)))
    height = graph.div(graph.sub(z, layer["base"]), thickness)
    offset = seed_offset(layer["seed"] + 17)
    lumps = graph.sub(graph.noise(graph.combine(graph.add(graph.div(x, tower), offset[0]), graph.add(graph.div(y, tower), offset[1]), graph.add(graph.div(z, tower), offset[2])), 1.0, 1.5, 0.5), 0.5)
    widening = graph.madd(graph.smooth(0.0, 0.6, height), 0.35, 0.65)
    tower_reach = graph.madd(lumps, tower * 0.9, graph.sub(graph.mul(widening, tower), distance))
    share = graph.clamp01(graph.div(downwind, length))
    width = graph.madd(share, length * 0.45, tower * 1.1)
    low = graph.madd(share, 0.07, ANVIL_LOW)
    high = graph.madd(share, -0.05, 1.0)
    anvil_reach = graph.minimum(graph.sub(width, sideways), graph.sub(length, downwind))
    anvil_reach = graph.minimum(anvil_reach, graph.add(downwind, tower * 1.4))
    anvil_reach = graph.minimum(anvil_reach, graph.mul(graph.sub(height, low), thickness))
    anvil_reach = graph.minimum(anvil_reach, graph.mul(graph.sub(high, height), thickness))
    anvil_reach = graph.madd(lumps, tower * 0.35, anvil_reach)
    return graph.mul(graph.maximum(tower_reach, anvil_reach), 0.25 / tower)


def column(graph, x, y, layer):
    """Column quantities for the sheet form: the cloud share above the point and its optical thickness."""
    u, v = layer_coordinates(graph, x, y, layer)
    field = footprint(graph, u, v, layer["seed"])
    excess = graph.sub(field, layer["threshold"])
    if layer["genus"] == "cumulonimbus":
        excess = anvil_excess(graph, x, y, layer["base"] + layer["thickness"] * 0.9, layer)
    inside = graph.smooth(0.0, layer["edge"] * span_of(layer["threshold"]) * 2.0, excess)
    share = graph.mul(graph.mul(column_share(graph, excess, layer), inside), towers(graph, u, v, layer))
    if layer["profile"] == "layer" and layer["fibres"] <= 0.0:
        share = graph.mul(share, rolls(graph, u, v, layer))
    if layer["fibres"] > 0.0:
        share = graph.mul(share, fibres(graph, u, v, layer["base"] + layer["thickness"] * 0.5, layer))
    depth = graph.mul(share, layer["extinction"] * layer["density"] * layer["thickness"] * 0.75)
    return share, depth, field
