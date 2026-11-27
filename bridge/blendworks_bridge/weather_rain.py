import math
import random

import bpy

from . import atmosphere_haze, cloud_field, sky_nodes, weather_objects
from .edge_order import canonical_edges

VEIL_START = 1200.0
VEIL_DISTANCES = (2500.0, 5000.0, 9000.0, 15_000.0, 25_000.0)
CURTAIN_CELL = 1600.0
STREAK_CELL = 55.0
SHAFT_FALL = 0.35
STREAK_LENGTH = 0.3
STREAK_WIDTH = 0.003
STREAK_NEAR = 2.0
STREAK_FAR = 25.0
STREAKS_PER_MM = 120
MAX_STREAKS = 6_000


def extinction(rate):
    """Extinction of rain per metre for a rain rate in mm/h (visibility about 3.9 / extinction)."""
    return 0.00025 * rate ** 0.63 if rate > 0.0 else 0.0


def mask(graph, x, y, source):
    """Where rain falls: under the thick parts of the source layer, in curtains with streaks."""
    seed = cloud_field.seed_offset(source["seed"] + 21)
    curtain = graph.noise(graph.combine(graph.add(graph.mul(x, 1.0 / CURTAIN_CELL), seed[0]), graph.add(graph.mul(y, 1.0 / CURTAIN_CELL), seed[1]), seed[2]), 1.0, 2.0, 0.5)
    streak = graph.noise(graph.combine(graph.add(graph.mul(x, 1.0 / STREAK_CELL), seed[1]), graph.add(graph.mul(y, 1.0 / STREAK_CELL), seed[2]), seed[0]), 1.0, 3.0, 0.6)
    texture = graph.mul(graph.smooth(0.42, 0.58, curtain), graph.madd(graph.smooth(0.3, 0.7, streak), 0.45, 0.55))
    share, _, _ = cloud_field.column(graph, x, y, source)
    return graph.mul(texture, graph.smooth(0.35, 0.8, share))


def veil(graph, view, dz, colour, rain, centre):
    """Rain curtains on cylinders around the observer, up to the cloud base, so they hang as vertical streaks."""
    source = rain["source"]
    sigma = extinction(rain["rate"]) * rain.get("veil", 1.0)
    base = source["base"]
    tangent = graph.div(dz, graph.math("SQRT", graph.maximum(graph.sub(1.0, graph.mul(dz, dz)), 1e-6)))
    vx, vy, _ = graph.separate(view)
    flat = graph.math("SQRT", graph.maximum(graph.add(graph.mul(vx, vx), graph.mul(vy, vy)), 1e-8))
    hx = graph.div(vx, flat)
    hy = graph.div(vy, flat)
    depth = None
    previous = VEIL_START
    for distance in VEIL_DISTANCES:
        step = distance - previous
        previous = distance
        x = graph.madd(hx, distance, centre[0])
        y = graph.madd(hy, distance, centre[1])
        under = graph.sub(1.0, graph.smooth(base * 0.85, base * 1.05, graph.mul(tangent, distance)))
        term = graph.mul(graph.mul(mask(graph, x, y, source), under), step)
        depth = term if depth is None else graph.add(depth, term)
    alpha = graph.sub(1.0, graph.exp(graph.mul(depth, -sigma)))
    return graph.mix(alpha, colour, graph.rgb(rain["colour"])), alpha


def shaft_material(name, source, rate):
    material = bpy.data.materials.new(name)
    tree = material.node_tree
    tree.nodes.clear()
    graph = sky_nodes.Graph(tree)
    geometry = graph.node("ShaderNodeNewGeometry")
    x, y, z = graph.separate(geometry.outputs["Position"])
    lean = SHAFT_FALL
    wind = math.radians(source["wind_direction"])
    sx = graph.madd(z, -lean * math.sin(wind), x)
    sy = graph.madd(z, -lean * math.cos(wind), y)
    centre = source["centre"]
    dx = graph.sub(sx, centre[0])
    dy = graph.sub(sy, centre[1])
    distance = graph.math("SQRT", graph.add(graph.mul(dx, dx), graph.mul(dy, dy)))
    core = graph.sub(1.0, graph.smooth(source["tower_radius"] * 0.2, source["tower_radius"] * 1.2, distance))
    seed = cloud_field.seed_offset(source["seed"] + 23)
    streak = graph.noise(graph.combine(graph.add(graph.mul(sx, 1.0 / STREAK_CELL), seed[0]), graph.add(graph.mul(sy, 1.0 / STREAK_CELL), seed[1]), graph.add(graph.mul(z, 1.0 / 4000.0), seed[2])), 1.0, 3.0, 0.6)
    curtain = graph.noise(graph.combine(graph.add(graph.mul(sx, 1.0 / CURTAIN_CELL), seed[1]), graph.add(graph.mul(sy, 1.0 / CURTAIN_CELL), seed[2]), seed[0]), 1.0, 2.0, 0.5)
    texture = graph.mul(graph.madd(graph.smooth(0.3, 0.7, streak), 0.75, 0.25), graph.smooth(0.25, 0.55, curtain))
    below = graph.sub(1.0, graph.smooth(source["base"] - 450.0, source["base"] - 50.0, z))
    density = graph.mul(graph.mul(graph.mul(core, texture), below), extinction(rate) * 2.5)
    scatter = graph.node("ShaderNodeVolumeScatter")
    scatter.inputs["Color"].default_value = (0.55, 0.57, 0.6, 1.0)
    scatter.inputs["Anisotropy"].default_value = 0.3
    graph.feed(scatter.inputs["Density"], density)
    absorb = graph.node("ShaderNodeVolumeAbsorption")
    absorb.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    graph.feed(absorb.inputs["Density"], graph.mul(density, 0.45))
    both = graph.node("ShaderNodeAddShader")
    tree.links.new(scatter.outputs[0], both.inputs[0])
    tree.links.new(absorb.outputs[0], both.inputs[1])
    output = graph.node("ShaderNodeOutputMaterial")
    tree.links.new(both.outputs[0], output.inputs["Volume"])
    return material


def add_shaft(scene, source, rate, visible):
    reach = source["tower_radius"] * 1.2
    lean = SHAFT_FALL * source["base"]
    centre = source["centre"]
    low = [centre[0] - reach - lean, centre[1] - reach - lean, 0.0]
    high = [centre[0] + reach + lean, centre[1] + reach + lean, source["base"] + 120.0]
    mesh = atmosphere_haze.box_mesh("Rain shaft", low, high)
    material = shaft_material("Rain shaft", source, rate)
    material.cycles.volume_step_rate = 0.3
    mesh.materials.append(material)
    obj = bpy.data.objects.new("Rain shaft", mesh)
    weather_objects.link(scene, obj, "rain_veil")
    obj.display_type = "BOUNDS"
    obj.hide_render = not visible
    return obj


def streak_material(brightness):
    material = bpy.data.materials.new("Rain streaks")
    tree = material.node_tree
    tree.nodes.clear()
    graph = sky_nodes.Graph(tree)
    coordinates = graph.node("ShaderNodeTexCoord")
    u, v, _ = graph.separate(coordinates.outputs["UV"])
    across = graph.sub(1.0, graph.smooth(0.0, 0.5, graph.math("ABSOLUTE", graph.sub(u, 0.5))))
    along = graph.mul(graph.smooth(0.0, 0.3, v), graph.sub(1.0, graph.smooth(0.7, 1.0, v)))
    opacity = graph.mul(graph.mul(across, along), 0.45)
    emission = graph.node("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.92, 0.95, 1.0, 1.0)
    emission.inputs["Strength"].default_value = brightness
    transparent = graph.node("ShaderNodeBsdfTransparent")
    mixed = graph.node("ShaderNodeMixShader")
    graph.feed(mixed.inputs[0], opacity)
    tree.links.new(transparent.outputs[0], mixed.inputs[1])
    tree.links.new(emission.outputs[0], mixed.inputs[2])
    output = graph.node("ShaderNodeOutputMaterial")
    tree.links.new(mixed.outputs[0], output.inputs["Surface"])
    material.surface_render_method = "BLENDED"
    return material


def streak_count(rate):
    return int(min(MAX_STREAKS, STREAKS_PER_MM * rate ** 0.8))


def add_streaks(scene, camera, rate, seed, wind_direction, brightness):
    """Falling drops near the camera as thin streaks, as a shutter of about 1/60 s draws them, facing the camera."""
    generator = random.Random(seed)
    matrix = camera.matrix_world
    origin = matrix.translation
    right = matrix.to_3x3().col[0].normalized()
    forward = (matrix.to_3x3().col[2] * -1.0).normalized()
    up = matrix.to_3x3().col[1].normalized()
    angle = camera.data.angle
    lean_x = math.sin(math.radians(wind_direction)) * 0.18
    lean_y = math.cos(math.radians(wind_direction)) * 0.18
    vertices, faces, uvs = [], [], []
    count = streak_count(rate)
    for index in range(count):
        depth = STREAK_NEAR + (STREAK_FAR - STREAK_NEAR) * generator.random() ** 1.6
        half = math.tan(angle / 2.0) * depth * 1.1
        centre = origin + forward * depth + right * generator.uniform(-half, half) + up * generator.uniform(-half * 0.75, half * 0.75)
        length = STREAK_LENGTH * generator.uniform(0.6, 1.3)
        fall = (lean_x * length, lean_y * length, -length)
        top = (centre.x - fall[0] / 2, centre.y - fall[1] / 2, centre.z - fall[2] / 2)
        bottom = (centre.x + fall[0] / 2, centre.y + fall[1] / 2, centre.z + fall[2] / 2)
        width = STREAK_WIDTH * (0.6 + 0.08 * depth)
        side = (right.x * width / 2, right.y * width / 2, right.z * width / 2)
        start = len(vertices)
        vertices.extend([
            (bottom[0] - side[0], bottom[1] - side[1], bottom[2] - side[2]),
            (bottom[0] + side[0], bottom[1] + side[1], bottom[2] + side[2]),
            (top[0] + side[0], top[1] + side[1], top[2] + side[2]),
            (top[0] - side[0], top[1] - side[1], top[2] - side[2]),
        ])
        faces.append((start, start + 1, start + 2, start + 3))
        uvs.extend([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    mesh = bpy.data.meshes.new("Rain streaks")
    mesh.from_pydata(vertices, [], faces)
    canonical_edges(mesh)
    layer = mesh.uv_layers.new(name="UVMap")
    for loop_index, loop in enumerate(mesh.loops):
        layer.data[loop_index].uv = uvs[loop.vertex_index]
    mesh.materials.append(streak_material(brightness))
    mesh.update()
    obj = bpy.data.objects.new("Rain streaks", mesh)
    weather_objects.link(scene, obj, "rain_streaks")
    for flag in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
        setattr(obj, flag, False)
    return obj, count
