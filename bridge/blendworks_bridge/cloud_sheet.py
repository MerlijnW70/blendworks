import math

import bpy

from . import cloud_field, sky_nodes, sky_sun, sky_world, weather_objects, weather_rain

EARTH_RADIUS = 6_371_000.0
AEROSOL_HEIGHT = 1500.0
PHASE_G = 0.8
DIFFUSE_G = 0.85
SIDE_LOW = 0.04
SIDE_HIGH = 0.3
GROUND_ALBEDO = 0.15
SWITCH_NODE = "Clouds Volume Switch"
SHADOW_SIZE_CAP = 200_000.0


def direction(graph):
    coordinates = graph.node("ShaderNodeTexCoord")
    return graph.vector("NORMALIZE", coordinates.outputs["Generated"])


def shell_distance(graph, dz, height):
    radius = EARTH_RADIUS
    b = graph.mul(dz, radius)
    root = graph.math("SQRT", graph.add(graph.mul(b, b), 2.0 * radius * height + height * height))
    return graph.sub(root, b)


def transmittance_diffuse(graph, depth):
    return graph.div(1.0, graph.madd(depth, 0.75 * (1.0 - DIFFUSE_G), 1.0))


def phase(graph, cosine):
    g = PHASE_G
    denominator = graph.power(graph.madd(cosine, -2.0 * g, 1.0 + g * g), 1.5)
    return graph.div((1.0 - g * g) / (4.0 * math.pi), denominator)


def scaled(graph, colour, factor):
    return graph.mix(1.0, graph.rgb(colour), graph.gray(factor), "MULTIPLY")


def layer_radiance(graph, layer, light, view, sun, depth, mu_view, alpha):
    dx, dy, _ = graph.separate(view)
    cos_horizontal = graph.add(graph.mul(dx, sun["horizontal"][0]), graph.mul(dy, sun["horizontal"][1]))
    cos_sun = graph.vector("DOT_PRODUCT", view, sun["vector"])
    diffuse = transmittance_diffuse(graph, depth)
    reflect = graph.sub(1.0, diffuse)
    side = graph.sub(1.0, graph.smooth(SIDE_LOW, SIDE_HIGH, mu_view))
    facing = graph.madd(cos_horizontal, -0.5, 0.5)
    below_sun = graph.mul(diffuse, sun["mu"])
    side_sun = graph.mul(graph.mul(reflect, sun["mu_side"]), graph.madd(facing, 1.4, 0.15))
    sun_share = graph.div(graph.mix_value(side, below_sun, side_sun), math.pi)
    forward = graph.mul(graph.mul(phase(graph, cos_sun), alpha), graph.exp(graph.mul(depth, -0.35)))
    sun_total = graph.add(sun_share, graph.mul(forward, 0.6))
    below_sky = graph.madd(reflect, GROUND_ALBEDO * 0.5, diffuse)
    side_sky = graph.madd(reflect, 0.35, 0.25)
    sky_share = graph.div(graph.mix_value(side, below_sky, side_sky), math.pi)
    lit = graph.mix(1.0, scaled(graph, light["sun"], sun_total), scaled(graph, light["sky"], sky_share), "ADD")
    tint = [value * layer["brightness"] for value in layer["tint"]]
    return graph.mix(1.0, lit, graph.rgb(tint), "MULTIPLY")


def sun_terms(graph, sky, layer):
    elevation = sky["elevation"]
    dip = math.degrees(math.sqrt(2.0 * (layer["base"] + layer["thickness"] * 0.5) / EARTH_RADIUS))
    lit = max(elevation + dip, 0.0)
    mu = math.sin(math.radians(max(lit, 0.5))) if elevation + dip > 0.0 else 0.0
    vector = sky_sun.direction(elevation, sky["azimuth"])
    horizontal = math.hypot(vector[0], vector[1]) or 1.0
    return {
        "vector": vector,
        "horizontal": (vector[0] / horizontal, vector[1] / horizontal),
        "mu": mu,
        "mu_side": math.cos(math.radians(max(lit, 0.0))) * (1.0 if elevation + dip > 0.0 else 0.0) * 0.8 + mu * 0.2,
    }


def aerial(graph, distance, height, visibility):
    sigma = 3.912 / visibility
    reach = AEROSOL_HEIGHT * (1.0 - math.exp(-height / AEROSOL_HEIGHT)) / height
    return graph.exp(graph.mul(distance, -sigma * reach))


def build(world, layers, sky, centre, cover_total, visibility, switch_on, rain=None):
    """Composite the sheet layers over the clear sky in the world, highest first; return the switch node."""
    nodes = sky_world.named_nodes(world)
    tree = world.node_tree
    graph = sky_nodes.Graph(tree, -3600, -600)
    view = direction(graph)
    _, _, dz = graph.separate(view)
    above = graph.smooth(-0.004, 0.012, dz)
    switch = graph.value(1.0 if switch_on else 0.0, SWITCH_NODE)
    colour = nodes[sky_world.CLEAR_NODE].outputs["Color"]
    airlight = graph.mix(cover_total, colour, graph.rgb(sky["overcast_air"]))
    through = None
    for layer in sorted(layers, key=lambda entry: -entry["base"]):
        light = layer["light"]
        height = layer["base"] + layer["thickness"] * 0.5
        distance = shell_distance(graph, dz, height)
        point = graph.vector("SCALE", view, None, distance)
        px, py, _ = graph.separate(point)
        x = graph.add(px, centre[0])
        y = graph.add(py, centre[1])
        share, depth, _ = cloud_field.column(graph, x, y, layer)
        mu_view = graph.div(graph.madd(dz, EARTH_RADIUS, distance), EARTH_RADIUS + height)
        slant = graph.maximum(mu_view, layer["min_mu"])
        alpha = graph.sub(1.0, graph.exp(graph.div(graph.mul(depth, -1.0), slant)))
        alpha = graph.mul(alpha, above)
        if layer["volume"] and layer["genus"] == "cumulonimbus":
            alpha = graph.mul(alpha, graph.sub(1.0, switch))
        elif layer["volume"]:
            beyond = graph.smooth(layer["radius"] * 0.85, layer["radius"], graph.math("SQRT", graph.add(graph.mul(px, px), graph.mul(py, py))))
            alpha = graph.mul(alpha, graph.mix_value(switch, 1.0, beyond))
        radiance = layer_radiance(graph, layer, light, view, sun_terms(graph, sky, layer), depth, mu_view, alpha)
        seen = graph.mix(aerial(graph, distance, height, visibility), airlight, radiance)
        colour = graph.mix(alpha, colour, seen)
        clear = graph.sub(1.0, alpha)
        through = clear if through is None else graph.mul(through, clear)
    if rain is not None:
        colour, veil = weather_rain.veil(graph, view, dz, colour, rain, centre)
        clear = graph.sub(1.0, veil)
        through = clear if through is None else graph.mul(through, clear)
    composite = nodes[sky_world.COMPOSITE_INPUT]
    tree.links.new(colour, composite.inputs[6])
    if through is not None:
        dimmed = graph.mix(1.0, nodes[sky_world.DISC_TERM].outputs[2], graph.gray(through), "MULTIPLY")
        tree.links.new(dimmed, composite.inputs[7])
    return switch


def shadow_material(name, layer, beyond_volume):
    material = bpy.data.materials.new(name)
    tree = material.node_tree
    tree.nodes.clear()
    graph = sky_nodes.Graph(tree)
    geometry = graph.node("ShaderNodeNewGeometry")
    x, y, _ = graph.separate(geometry.outputs["Position"])
    _, depth, _ = cloud_field.column(graph, x, y, layer)
    opacity = graph.sub(1.0, graph.exp(graph.mul(depth, -1.0)))
    if beyond_volume is not None:
        centre, radius, switch = beyond_volume
        dx = graph.sub(x, centre[0])
        dy = graph.sub(y, centre[1])
        far = graph.smooth(radius * 0.85, radius, graph.math("SQRT", graph.add(graph.mul(dx, dx), graph.mul(dy, dy))))
        opacity = graph.mul(opacity, graph.mix_value(graph.value(switch, SWITCH_NODE), 1.0, far))
    transparent = graph.node("ShaderNodeBsdfTransparent")
    block = graph.node("ShaderNodeBsdfDiffuse")
    block.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    mixed = graph.node("ShaderNodeMixShader")
    graph.feed(mixed.inputs[0], opacity)
    tree.links.new(transparent.outputs[0], mixed.inputs[1])
    tree.links.new(block.outputs[0], mixed.inputs[2])
    output = graph.node("ShaderNodeOutputMaterial")
    tree.links.new(mixed.outputs[0], output.inputs["Surface"])
    material.surface_render_method = "DITHERED"
    material.use_transparent_shadow = True
    return material


def shadow_plane(scene, name, layer, centre, size, beyond_volume):
    half = size / 2.0
    height = layer["base"] + layer["thickness"] * 0.5
    mesh = bpy.data.meshes.new(name)
    corners = [(centre[0] - half, centre[1] - half, height), (centre[0] + half, centre[1] - half, height),
               (centre[0] + half, centre[1] + half, height), (centre[0] - half, centre[1] + half, height)]
    mesh.from_pydata(corners, [], [(0, 1, 2, 3)])
    mesh.update()
    mesh.materials.append(shadow_material(name, layer, beyond_volume))
    obj = bpy.data.objects.new(name, mesh)
    weather_objects.link(scene, obj, "cloud_shadow")
    for flag in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(obj, flag, False)
    obj.visible_shadow = True
    obj.display_type = "WIRE"
    return obj


def shadow_size(layer, elevation, radius):
    height = layer["base"] + layer["thickness"] * 0.5
    reach = height / math.tan(math.radians(max(elevation, 1.0)))
    return min(max(2.4 * radius, 2.0 * (reach + radius * 0.5)), SHADOW_SIZE_CAP)
