import bpy

from . import atmosphere_haze, cloud_field, sky_nodes, weather_objects

STEP_RATE = 0.05
FORWARD_G = 0.92
FORWARD_SHARE = 0.5
STEP_REFERENCE = 30_000.0
EDGE_FADE = 0.85
HEIGHT_MARGIN = 0.12


def domain_bounds(layer, centre, radius):
    if layer["genus"] == "cumulonimbus":
        reach = layer["anvil_radius"] * 1.9 + layer["tower_radius"] * 1.6
        middle = layer["centre"]
        low = [middle[0] - reach, middle[1] - reach, layer["base"] - 50.0]
        high = [middle[0] + reach, middle[1] + reach, layer["base"] + layer["thickness"] * (1.0 + HEIGHT_MARGIN)]
        return low, high
    margin = layer["thickness"] * HEIGHT_MARGIN
    low = [centre[0] - radius, centre[1] - radius, layer["base"] - 2.0 * margin]
    high = [centre[0] + radius, centre[1] + radius, layer["base"] + layer["thickness"] + margin]
    return low, high


def radial_fade(graph, position, centre, radius):
    x, y, _ = graph.separate(position)
    dx = graph.sub(x, centre[0])
    dy = graph.sub(y, centre[1])
    distance = graph.math("SQRT", graph.add(graph.mul(dx, dx), graph.mul(dy, dy)))
    return graph.sub(1.0, graph.smooth(radius * EDGE_FADE, radius, distance))


def material(name, layer, centre, radius):
    material = bpy.data.materials.new(name)
    tree = material.node_tree
    tree.nodes.clear()
    graph = sky_nodes.Graph(tree)
    geometry = graph.node("ShaderNodeNewGeometry")
    position = geometry.outputs["Position"]
    extinction = cloud_field.density(graph, position, layer)
    if layer["genus"] != "cumulonimbus":
        extinction = graph.mul(extinction, radial_fade(graph, position, centre, radius))
    albedo = layer["albedo"]
    forward = lobe(graph, "Cloud Scatter", extinction, albedo, FORWARD_G, FORWARD_SHARE)
    broad = lobe(graph, "Cloud Scatter Broad", extinction, albedo, broad_g(layer["anisotropy"]), 1.0 - FORWARD_SHARE)
    absorb = graph.node("ShaderNodeVolumeAbsorption")
    absorb.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    graph.feed(absorb.inputs["Density"], graph.mul(extinction, 1.0 - albedo))
    scattered = graph.node("ShaderNodeAddShader")
    tree.links.new(forward.outputs[0], scattered.inputs[0])
    tree.links.new(broad.outputs[0], scattered.inputs[1])
    both = graph.node("ShaderNodeAddShader")
    tree.links.new(scattered.outputs[0], both.inputs[0])
    tree.links.new(absorb.outputs[0], both.inputs[1])
    output = graph.node("ShaderNodeOutputMaterial")
    tree.links.new(both.outputs[0], output.inputs["Volume"])
    return material


def broad_g(mean):
    """The second lobe's anisotropy that keeps the mixture's mean cosine at the genus's anisotropy."""
    return (mean - FORWARD_SHARE * FORWARD_G) / (1.0 - FORWARD_SHARE)


def lobe(graph, name, extinction, albedo, anisotropy, share):
    scatter = graph.node("ShaderNodeVolumeScatter", name)
    scatter.phase = "HENYEY_GREENSTEIN"
    scatter.inputs["Anisotropy"].default_value = anisotropy
    scatter.inputs["Color"].default_value = (albedo, albedo, albedo, 1.0)
    graph.feed(scatter.inputs["Density"], graph.mul(extinction, share))
    return scatter


def step_rate(low, high):
    width = max(high[0] - low[0], high[1] - low[1], high[2] - low[2])
    return min(1.0, STEP_RATE * STEP_REFERENCE / width)


def add_domain(scene, name, layer, centre, radius, visible):
    low, high = domain_bounds(layer, centre, radius)
    mesh = atmosphere_haze.box_mesh(name, low, high)
    cloud = material(name, layer, centre, radius)
    cloud.cycles.volume_step_rate = step_rate(low, high)
    mesh.materials.append(cloud)
    obj = bpy.data.objects.new(name, mesh)
    weather_objects.link(scene, obj, "cloud_volume")
    obj.display_type = "BOUNDS"
    obj.hide_render = not visible
    obj.visible_shadow = True
    return obj
