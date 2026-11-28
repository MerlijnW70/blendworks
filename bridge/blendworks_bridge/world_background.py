"""World background surface: reads, describes and replaces it."""

import json

import bpy

from . import weather_objects
from .errors import failed

SKY_PROPERTY = "blendworks_sky"
CLOUDS_PROPERTY = "blendworks_clouds"
DEFAULT_COLOR = (0.050876, 0.050876, 0.050876)
DEFAULT_NAME = "World"


def output_node(tree):
    active = [node for node in tree.nodes if node.type == "OUTPUT_WORLD" and node.is_active_output]
    if active:
        return active[0]
    return next((node for node in tree.nodes if node.type == "OUTPUT_WORLD"), None)


def upstream(socket):
    found = set()
    pending = [link.from_node for link in socket.links]
    while pending:
        node = pending.pop()
        if node.name in found:
            continue
        found.add(node.name)
        for item in node.inputs:
            pending.extend(link.from_node for link in item.links)
    return found


def surface_kind(world):
    """What drives the background: none, colour, image, sky, sky_clouds or nodes."""
    if world is None:
        return "none"
    if world.get(SKY_PROPERTY) is not None:
        return "sky_clouds" if world.get(CLOUDS_PROPERTY) is not None else "sky"
    tree = world.node_tree
    if tree is None:
        return "colour"
    output = output_node(tree)
    if output is None or not output.inputs["Surface"].is_linked:
        return "none"
    names = upstream(output.inputs["Surface"])
    types = {tree.nodes[name].type for name in names}
    if "TEX_ENVIRONMENT" in types or "TEX_IMAGE" in types:
        return "image"
    if "TEX_SKY" in types:
        return "sky"
    if types <= {"BACKGROUND", "RGB"}:
        return "colour"
    return "nodes"


def describe(world):
    kind = surface_kind(world)
    entry = {"kind": kind, "world": world.name if world is not None else None}
    if kind == "image":
        images = [node.image.name for node in world.node_tree.nodes if node.type in ("TEX_ENVIRONMENT", "TEX_IMAGE") and node.image is not None]
        entry["images"] = sorted(images)
    if kind in ("sky", "sky_clouds") and world.get(SKY_PROPERTY) is not None:
        settings = json.loads(world[SKY_PROPERTY])
        entry["sun"] = {"elevation": settings.get("elevation"), "azimuth": settings.get("azimuth")}
    if kind == "sky_clouds":
        entry["cloud_layers"] = len(json.loads(world[CLOUDS_PROPERTY]).get("layers", []))
    return entry


def own_world(scene):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new(DEFAULT_NAME)
        scene.world = world
    elif world.users > 1 + int(world.use_fake_user):
        world = world.copy()
        scene.world = world
    if world.node_tree is None:
        raise failed(f"world {world.name} has no node tree")
    return world


def clear_surface(world):
    """Remove every node that does not feed the world's volume, and the sky settings; returns the output node."""
    tree = world.node_tree
    output = output_node(tree)
    keep = upstream(output.inputs["Volume"]) if output is not None else set()
    for node in list(tree.nodes):
        if node != output and node.name not in keep:
            tree.nodes.remove(node)
    if output is None:
        output = tree.nodes.new("ShaderNodeOutputWorld")
    output.is_active_output = True
    output.location = (300, 0)
    for key in (SKY_PROPERTY, CLOUDS_PROPERTY):
        if key in world:
            del world[key]
    world.cycles.sampling_method = "AUTOMATIC"
    return output


def replace(scene, keep_weather=False):
    """Take the world for a new background: report what drove it, clear it, and drop the sky's lamp, clouds and weather."""
    before = describe(scene.world)
    world = own_world(scene)
    removed = [] if keep_weather else weather_objects.remove_all(scene)
    output = clear_surface(world)
    replaced = {"background": before["kind"], "world": before["world"]}
    for key in ("images", "sun", "cloud_layers"):
        if key in before:
            replaced[key] = before[key]
    if removed:
        replaced["objects"] = removed
    return world, output, replaced


def uniform(world, output, color, strength):
    tree = world.node_tree
    background = tree.nodes.new("ShaderNodeBackground")
    background.location = (0, 0)
    background.inputs["Color"].default_value = list(color) + [1.0]
    background.inputs["Strength"].default_value = strength
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    world.color = color
    return background


def reset_default(scene):
    """A fresh default world: a uniform grey background of strength 1, as Blender's own startup world."""
    old = scene.world
    scene.world = None
    if old is not None and old.users - int(old.use_fake_user) == 0:
        bpy.data.worlds.remove(old)
    world = bpy.data.worlds.new(DEFAULT_NAME)
    scene.world = world
    output = clear_surface(world)
    uniform(world, output, DEFAULT_COLOR, 1.0)
    return world
