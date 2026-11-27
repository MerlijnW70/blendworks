import json
import math

import bpy
import numpy as np
from mathutils import Vector

from .edge_order import canonical_edges

KOSCHMIEDER = -math.log(0.02)
SCENE_PROPERTY = "blendworks_atmosphere"
DOMAIN_NAME = "Atmosphere"
DOMAIN_FLAG = "blendworks_atmosphere_domain"
ADD_NODE = "Atmosphere Add"
MATERIAL_NAME = "Atmosphere"
VOLUME_NODE = "Atmosphere Scatter"
SKY_ROWS = 32
SKY_PROPERTY = "blendworks_sky"
CLOUDS_PROPERTY = "blendworks_clouds"
FLAT_RISE = 1e-6


def extinction(visibility):
    return KOSCHMIEDER / visibility


def layers_of(settings):
    """(extinction, base, falloff, top) per layer. The haze grows without bound below its base; ground fog has its full
    density everywhere below its top (base plus thickness) and falls off above it, so it is bounded below."""
    layers = [(extinction(settings["visibility"]), settings["base_height"], settings.get("height_falloff"), None)]
    fog = settings.get("ground_fog")
    if fog is not None:
        base = fog.get("base", settings["base_height"])
        layers.append((extinction(fog["visibility"]), base, fog["height"], base + fog.get("thickness", 0.0)))
    return layers


def layer_density(sigma, base, scale, top, z):
    if scale is None:
        return sigma
    if top is None:
        return sigma * math.exp(-(z - base) / scale)
    return sigma * min(1.0, math.exp(-(z - top) / scale))


def density_at(settings, z):
    return sum(layer_density(*layer, z) for layer in layers_of(settings))


def capped_integral(z, top, scale):
    """Antiderivative of min(1, exp(-(z - top) / scale)) in z, continuous at the top."""
    above = -scale * np.exp(-np.maximum(z - top, 0.0) / scale)
    return np.where(z <= top, z - top - scale, above)


def optical_depth(settings, start_z, end_z, distance):
    start_z = np.asarray(start_z, dtype=np.float64)
    end_z = np.asarray(end_z, dtype=np.float64)
    distance = np.asarray(distance, dtype=np.float64)
    total = np.zeros(np.broadcast(start_z, end_z, distance).shape)
    rise = end_z - start_z
    flat = np.abs(rise) < FLAT_RISE
    safe_rise = np.where(flat, 1.0, rise)
    for sigma, base, scale, top in layers_of(settings):
        if scale is None:
            total = total + sigma * distance
            continue
        if top is not None:
            level = np.minimum(1.0, np.exp(-(start_z - top) / scale))
            sloped = sigma * distance * (capped_integral(end_z, top, scale) - capped_integral(start_z, top, scale)) / safe_rise
            total = total + np.where(flat, sigma * distance * level, sloped)
            continue
        start = np.exp(-(start_z - base) / scale)
        end = np.exp(-(end_z - base) / scale)
        sloped = sigma * distance * scale * (start - end) / safe_rise
        total = total + np.where(flat, sigma * distance * start, sloped)
    return total


def transmittance(settings, start_z, end_z, distance):
    tint = np.asarray(settings["tint"], dtype=np.float64)
    depth = optical_depth(settings, start_z, end_z, distance)
    return np.exp(-depth[..., None] * tint)


def box_span(origin, directions, low, high):
    """Distances along each ray where it enters and leaves the box; a ray that misses gets entry = exit = 0."""
    low = np.asarray(low, dtype=np.float64)
    high = np.asarray(high, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        inverse = 1.0 / directions
        first = (low - origin) * inverse
        second = (high - origin) * inverse
    parallel = directions == 0.0
    inside_slab = (origin >= low) & (origin <= high)
    near = np.where(parallel, np.where(inside_slab, -np.inf, np.inf), np.minimum(first, second))
    far = np.where(parallel, np.where(inside_slab, np.inf, -np.inf), np.maximum(first, second))
    enter = np.maximum(np.max(near, axis=-1), 0.0)
    leave = np.min(far, axis=-1)
    hit = leave > enter
    return np.where(hit, enter, 0.0), np.where(hit, leave, 0.0)


def pixel_rays(scene, camera, width, height):
    frame = camera.data.view_frame(scene=scene)
    xs = [corner.x for corner in frame]
    ys = [corner.y for corner in frame]
    plane = frame[0].z
    left, right, bottom, top = min(xs), max(xs), min(ys), max(ys)
    columns = left + (np.arange(width) + 0.5) / width * (right - left)
    rows = top - (np.arange(height) + 0.5) / height * (top - bottom)
    grid_x, grid_y = np.meshgrid(columns, rows)
    local = np.stack([grid_x, grid_y, np.full_like(grid_x, plane)], axis=-1) / -plane
    rotation = np.array(camera.matrix_world.to_3x3().normalized())
    return local @ rotation.T


def depth_haze(scene, camera, rgb, depth, settings):
    height, width = depth.shape
    origin = np.array(camera.matrix_world.translation)
    rays = pixel_rays(scene, camera, width, height)
    lengths = np.linalg.norm(rays, axis=-1)
    directions = rays / lengths[..., None]
    distance = depth * lengths
    from . import mist_depth
    rgb = mist_depth.apply(rgb, origin, directions, distance, settings["airlight"], scene, box_span)
    start = np.zeros_like(distance)
    if settings["domain"] == "box":
        low, high = settings["bounds"]
        enter, leave = box_span(origin, directions, low, high)
        start = np.minimum(enter, distance)
        distance = np.minimum(distance, leave)
    start_z = origin[2] + directions[..., 2] * start
    end_z = origin[2] + directions[..., 2] * distance
    through = transmittance(settings, start_z, end_z, distance - start).astype(np.float32)
    airlight = np.asarray(settings["airlight"], dtype=np.float32)
    return rgb * through + airlight * (1.0 - through)


def world_background(world):
    if world is None or world.node_tree is None:
        return None
    output = next((node for node in world.node_tree.nodes if node.type == "OUTPUT_WORLD" and node.is_active_output), None)
    if output is None or not output.inputs["Surface"].is_linked:
        return None
    node = output.inputs["Surface"].links[0].from_node
    return node if node.type == "BACKGROUND" else None


def sky_radiance(image):
    """Cosine-weighted mean radiance of the upper hemisphere, read from evenly spaced rows only (no copy of the image)."""
    width, height = image.size
    half = height // 2
    count = min(half, SKY_ROWS * 4)
    if count == 0:
        return np.array(image.pixels[:3] if len(image.pixels) >= 3 else (0.0, 0.0, 0.0), dtype=np.float64)
    channels = image.channels
    total = np.zeros(3)
    weights = 0.0
    for step in range(count):
        fraction = (step + 0.5) / count
        row = min(height - 1, half + int(fraction * half))
        values = np.asarray(image.pixels[row * width * channels : (row + 1) * width * channels], dtype=np.float64)
        total += math.cos(fraction * math.pi / 2.0) * values.reshape(width, channels)[:, :3].mean(axis=0)
        weights += math.cos(fraction * math.pi / 2.0)
    return total / weights


def sky_airlight(world):
    """Mean radiance of the procedural sky, greyed by its cloud cover, as the sky and clouds commands store it."""
    settings = json.loads(world[SKY_PROPERTY])
    colour = np.asarray(settings["sky_mean"], dtype=np.float64)
    clouds = world.get(CLOUDS_PROPERTY)
    if isinstance(clouds, str):
        cover = float(json.loads(clouds).get("cover", 0.0))
        grey = float(np.dot(colour, (0.2126, 0.7152, 0.0722))) * 1.6
        colour = colour * (1.0 - cover) + grey * cover
    return [round(float(value), 6) for value in colour]


def estimated_airlight(world):
    if world is not None and isinstance(world.get(SKY_PROPERTY), str):
        return sky_airlight(world)
    background = world_background(world)
    if background is None:
        colour = list(world.color) if world is not None else [0.05, 0.05, 0.05]
        return [round(float(value), 6) for value in colour[:3]]
    strength = float(background.inputs["Strength"].default_value)
    colour_input = background.inputs["Color"]
    source = colour_input.links[0].from_node if colour_input.is_linked else None
    if source is not None and source.type == "TEX_ENVIRONMENT" and source.image is not None and source.image.size[0] > 0:
        colour = sky_radiance(source.image)
    else:
        colour = np.array(colour_input.default_value[:3])
    return [round(float(value) * strength, 6) for value in colour]


def stored(scene):
    text = scene.get(SCENE_PROPERTY)
    if not isinstance(text, str):
        return None
    settings = json.loads(text)
    present = domain_object(settings) is not None if settings["domain"] == "box" else world_volume_node(scene) is not None
    return settings if present else None


def store(scene, settings):
    scene[SCENE_PROPERTY] = json.dumps(settings, sort_keys=True)


def forget(scene):
    if SCENE_PROPERTY in scene:
        del scene[SCENE_PROPERTY]


def is_domain(obj):
    return bool(obj.get(DOMAIN_FLAG, False))


def domain_object(settings):
    name = settings.get("object")
    return bpy.data.objects.get(name) if name else None


def world_volume_node(scene):
    world = scene.world
    if world is None or world.node_tree is None:
        return None
    return world.node_tree.nodes.get(VOLUME_NODE)


class VolumeHidden:
    def __init__(self, scene, settings):
        self.scene = scene
        self.settings = settings
        self.saved = []

    def __enter__(self):
        if self.settings is None:
            return self
        target = domain_object(self.settings)
        if target is not None:
            self.saved.append((target, "hide_render", target.hide_render))
            target.hide_render = True
        node = world_volume_node(self.scene)
        if node is not None:
            self.saved.append((node, "mute", node.mute))
            node.mute = True
        from . import mist_depth
        for mist in mist_depth.mist_objects(self.scene):
            self.saved.append((mist, "hide_render", mist.hide_render))
            mist.hide_render = True
        return self

    def __exit__(self, kind, error, trace):
        for owner, name, value in reversed(self.saved):
            setattr(owner, name, value)
        return False


def density_socket(tree, settings, position_z):
    total = None
    for index, (sigma, base, scale, top) in enumerate(layers_of(settings)):
        if scale is None:
            value = tree.nodes.new("ShaderNodeValue")
            value.outputs[0].default_value = sigma
            term = value.outputs[0]
        else:
            term = exponential(tree, position_z, sigma, base if top is None else top, scale, capped=top is not None)
        if total is None:
            total = term
        else:
            add = math_node(tree, "ADD", (-200, -200 * index))
            tree.links.new(total, add.inputs[0])
            tree.links.new(term, add.inputs[1])
            total = add.outputs[0]
    return total


def math_node(tree, operation, location, second=None):
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = operation
    node.location = location
    if second is not None:
        node.inputs[1].default_value = second
    return node


def exponential(tree, position_z, sigma, base, scale, capped=False):
    shifted = math_node(tree, "SUBTRACT", (-800, 0), base)
    tree.links.new(position_z, shifted.inputs[0])
    scaled = math_node(tree, "DIVIDE", (-650, 0), -scale)
    tree.links.new(shifted.outputs[0], scaled.inputs[0])
    raised = math_node(tree, "EXPONENT", (-500, 0))
    tree.links.new(scaled.outputs[0], raised.inputs[0])
    if capped:
        bounded = math_node(tree, "MINIMUM", (-425, 0), 1.0)
        tree.links.new(raised.outputs[0], bounded.inputs[0])
        raised = bounded
    weighted = math_node(tree, "MULTIPLY", (-350, 0), sigma)
    tree.links.new(raised.outputs[0], weighted.inputs[0])
    return weighted.outputs[0]


def scatter_node(tree, settings):
    scatter = tree.nodes.new("ShaderNodeVolumeScatter")
    scatter.name = VOLUME_NODE
    scatter.inputs["Color"].default_value = list(settings["tint"]) + [1.0]
    scatter.inputs["Anisotropy"].default_value = settings["anisotropy"]
    return scatter


def volume_material(settings):
    material = bpy.data.materials.new(MATERIAL_NAME)
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    scatter = scatter_node(tree, settings)
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    separate = tree.nodes.new("ShaderNodeSeparateXYZ")
    geometry.location = (-1200, 0)
    separate.location = (-1000, 0)
    tree.links.new(geometry.outputs["Position"], separate.inputs[0])
    tree.links.new(density_socket(tree, settings, separate.outputs["Z"]), scatter.inputs["Density"])
    tree.links.new(scatter.outputs[0], output.inputs["Volume"])
    return material


def box_mesh(name, low, high):
    corners = [Vector((x, y, z)) for z in (low[2], high[2]) for y in (low[1], high[1]) for x in (low[0], high[0])]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(corner) for corner in corners], [], faces)
    canonical_edges(mesh)
    mesh.update()
    return mesh


def add_world_volume(world, settings):
    """Add the scatter node to the world's volume; a volume that is already linked stays and is added to."""
    tree = world.node_tree
    output = next((node for node in tree.nodes if node.type == "OUTPUT_WORLD" and node.is_active_output), None)
    if output is None:
        output = tree.nodes.new("ShaderNodeOutputWorld")
    scatter = scatter_node(tree, settings)
    scatter.inputs["Density"].default_value = extinction(settings["visibility"])
    scatter.location = (output.location.x - 450, output.location.y - 250)
    socket = output.inputs["Volume"]
    if socket.is_linked:
        previous = socket.links[0].from_socket
        combined = tree.nodes.new("ShaderNodeAddShader")
        combined.name = ADD_NODE
        combined.location = (output.location.x - 220, output.location.y - 250)
        tree.links.new(previous, combined.inputs[0])
        tree.links.new(scatter.outputs[0], combined.inputs[1])
        tree.links.new(combined.outputs[0], socket)
    else:
        tree.links.new(scatter.outputs[0], socket)


def remove_world_volume(world):
    if world is None or world.node_tree is None:
        return False
    tree = world.node_tree
    node = tree.nodes.get(VOLUME_NODE)
    if node is None:
        return False
    combined = tree.nodes.get(ADD_NODE)
    if combined is not None:
        targets = [link.to_socket for link in combined.outputs[0].links]
        if combined.inputs[0].is_linked:
            source = combined.inputs[0].links[0].from_socket
            for target in targets:
                tree.links.new(source, target)
        tree.nodes.remove(combined)
    tree.nodes.remove(node)
    return True
