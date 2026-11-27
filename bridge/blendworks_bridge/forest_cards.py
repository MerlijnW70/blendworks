"""Impostor cards, their material, the canopy surface far out, and the calibration that makes a card as bright as the tree
it stands for under the scene's own light."""
import os
import shutil
import tempfile

import bpy
import numpy
from mathutils import Matrix, Vector

from . import exr_read, impostors
from .errors import failed
from .land_material import FOREST_ATTRIBUTE, SURFACE_NODE, attribute
from .liquid_world import write_point_attribute
from .nodes import Graph

TURN_ATTRIBUTE = "dl_turn"
CANOPY_NODE = "dl_canopy_mix"
TRANSLUCENCY = 0.25
CALIBRATION_PIXELS = 160
CALIBRATION_SAMPLES = 24
GAIN_RANGE = (0.4, 2.5)
LUMINANCE = numpy.array([0.2126, 0.7152, 0.0722])


UV_LAYERS = ("UVMap", "UVFrame1", "UVFrame2", "UVFrame3")
WEIGHT_ATTRIBUTES = ("dl_frame0", "dl_frame1", "dl_frame2", "dl_frame3")


def card_mesh(name, trees, frames, variants):
    """One mesh of square cards: per tree a quad facing its viewer, with a UV map into each of the four atlas frames
    around the view direction and their blend weights."""
    count = len(trees["pivot"])
    corners = numpy.zeros((count, 4, 3))
    uvs = numpy.zeros((4, count, 4, 2))
    weights = numpy.zeros((4, count))
    columns = frames * variants
    for index in range(count):
        variant = int(trees["variant"][index])
        direction = trees["view"][index]
        corners[index] = impostors.card_corners(trees["pivot"][index], trees["turn"][index], direction, trees["half"][index])
        for slot, (column, row, weight) in enumerate(impostors.blend_frames(frames, direction)):
            u0, u1 = (variant * frames + column) / columns, (variant * frames + column + 1) / columns
            v0, v1 = row / frames, (row + 1) / frames
            uvs[slot, index] = [[u0, v0], [u1, v0], [u1, v1], [u0, v1]]
            weights[slot, index] = weight
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(count * 4)
    mesh.vertices.foreach_set("co", corners.astype(numpy.float32).ravel())
    mesh.loops.add(count * 4)
    mesh.polygons.add(count)
    mesh.loops.foreach_set("vertex_index", numpy.arange(count * 4, dtype=numpy.int32))
    mesh.polygons.foreach_set("loop_start", numpy.arange(0, count * 4, 4, dtype=numpy.int32))
    mesh.polygons.foreach_set("loop_total", numpy.full(count, 4, dtype=numpy.int32))
    mesh.update(calc_edges=True)
    for slot, layer_name in enumerate(UV_LAYERS):
        layer = mesh.uv_layers.new(name=layer_name)
        layer.uv.foreach_set("vector", uvs[slot].astype(numpy.float32).ravel())
        write_point_attribute(mesh, WEIGHT_ATTRIBUTES[slot], numpy.repeat(weights[slot].astype(numpy.float32), 4))
    write_point_attribute(mesh, TURN_ATTRIBUTE, numpy.repeat(numpy.asarray(trees["turn"], dtype=numpy.float32), 4))
    mesh.update()
    return mesh


def blended(graph, colour, normal):
    """Alpha, colour and normal of the four frames, each weighted by its blend weight and alpha (premultiplied)."""
    alpha, premultiplied, normal_sum = None, None, None
    for layer_name, weight_name in zip(UV_LAYERS, WEIGHT_ATTRIBUTES):
        uv = graph.node("ShaderNodeUVMap", uv_map=layer_name).outputs["UV"]
        colour_texture = graph.node("ShaderNodeTexImage", {"Vector": uv}, image=colour, interpolation="Linear")
        normal_texture = graph.node("ShaderNodeTexImage", {"Vector": uv}, image=normal, interpolation="Linear")
        weight = graph.math("MULTIPLY", graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=weight_name).outputs["Fac"],
                            colour_texture.outputs["Alpha"])
        tinted = graph.vector_math("SCALE", colour_texture.outputs["Color"], None, weight)
        unpack = graph.node("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
        graph.set(unpack.inputs[0], normal_texture.outputs["Color"])
        unpack.inputs[1].default_value = (2.0, 2.0, 2.0)
        unpack.inputs[2].default_value = (-1.0, -1.0, -1.0)
        bent = graph.vector_math("SCALE", unpack.outputs["Vector"], None, weight)
        alpha = weight if alpha is None else graph.math("ADD", alpha, weight)
        premultiplied = tinted if premultiplied is None else graph.vector_math("ADD", premultiplied, tinted)
        normal_sum = bent if normal_sum is None else graph.vector_math("ADD", normal_sum, bent)
    straight = graph.vector_math("DIVIDE", premultiplied, graph.node("ShaderNodeCombineXYZ", {
        "X": graph.math("MAXIMUM", alpha, 1e-4), "Y": graph.math("MAXIMUM", alpha, 1e-4), "Z": graph.math("MAXIMUM", alpha, 1e-4)}).outputs[0])
    return alpha, straight, normal_sum


def impostor_material(name, colour, normal, gain):
    material = bpy.data.materials.new(name)
    material.surface_render_method = "DITHERED"
    graph = Graph(material.node_tree)
    graph.nodes.clear()
    output = graph.node("ShaderNodeOutputMaterial")
    alpha, straight, local = blended(graph, colour, normal)
    tinted = graph.mix(1.0, straight, list(gain), blend="MULTIPLY")
    turn = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=TURN_ATTRIBUTE).outputs["Fac"]
    rotate = graph.node("ShaderNodeVectorRotate", {"Vector": local, "Angle": turn}, rotation_type="Z_AXIS")
    world_normal = graph.vector_math("NORMALIZE", rotate.outputs["Vector"])
    surface = graph.node("ShaderNodeBsdfPrincipled", {"Base Color": tinted, "Roughness": 0.6, "Normal": world_normal})
    translucent = graph.node("ShaderNodeBsdfTranslucent", {"Color": tinted, "Normal": world_normal})
    leaf = graph.node("ShaderNodeMixShader", {"Fac": TRANSLUCENCY})
    graph.set(leaf.inputs[1], surface.outputs[0])
    graph.set(leaf.inputs[2], translucent.outputs[0])
    clear = graph.node("ShaderNodeBsdfTransparent")
    cut = graph.node("ShaderNodeMixShader")
    graph.set(cut.inputs[0], graph.math("MINIMUM", alpha, 1.0))
    graph.set(cut.inputs[1], clear.outputs[0])
    graph.set(cut.inputs[2], leaf.outputs[0])
    graph.set(output.inputs["Surface"], cut.outputs[0])
    return material


def set_gain(material, gain):
    node = next(node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeMix" and node.blend_type == "MULTIPLY")
    node.inputs[7].default_value = list(gain) + [1.0]


def add_canopy(material, colour, crown):
    """Mix the canopy into the land's ground colour where the canopy share is: the crowns' colour, darker in the gaps of a
    crown-sized cell pattern."""
    tree = material.node_tree
    principled = tree.nodes.get(SURFACE_NODE)
    if principled is None:
        raise failed(f"{material.name} is not a distant land material")
    remove_canopy(material)
    graph = Graph(tree)
    base = graph.source_of(principled.inputs["Base Color"])
    position = graph.node("ShaderNodeNewGeometry").outputs["Position"]
    cells = graph.voronoi(position, 1.0 / crown).outputs["Distance"]
    gaps = graph.map_range(cells, 0.15, 0.6, 1.0, 0.45)
    shaded = graph.mix(1.0, list(colour), graph.node("ShaderNodeCombineXYZ", {"X": gaps, "Y": gaps, "Z": gaps}).outputs[0], blend="MULTIPLY")
    mixed = graph.mix(attribute(graph, FOREST_ATTRIBUTE), base, shaded)
    mixed.node.name = CANOPY_NODE
    mixed.node.label = "canopy"
    graph.set(principled.inputs["Base Color"], mixed)


def remove_canopy(material):
    tree = material.node_tree
    node = tree.nodes.get(CANOPY_NODE)
    if node is None:
        return False
    principled = tree.nodes.get(SURFACE_NODE)
    source = next((link.from_socket for link in tree.links if link.to_node == node and link.to_socket.identifier.startswith("A")), None)
    if source is not None and principled is not None:
        tree.links.new(source, principled.inputs["Base Color"])
    tree.nodes.remove(node)
    return True


class Calibration:
    """Renders a row of real trees and the same row as cards from the camera's direction at the switch distance, under
    the scene's world and lights, and compares their mean colour and silhouettes."""

    def __init__(self, scene, collections, spheres, frames, pixels=CALIBRATION_PIXELS):
        self.scene, self.collections, self.spheres, self.frames, self.pixels = scene, collections, spheres, frames, pixels

    def run(self, material, toward, distance):
        folder = tempfile.mkdtemp(prefix="blendworks-forest-")
        probe = bpy.data.scenes.new("blendworks forest calibration")
        made, meshes = [], []
        try:
            self.prepare(probe, toward, distance, made)
            trees = self.render(probe, folder, "trees")
            for obj in made:
                if obj.instance_type == "COLLECTION":
                    obj.hide_render = True
            self.cards(probe, material, toward, distance, made, meshes)
            seen = self.render(probe, folder, "cards")
        finally:
            for obj in made:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if isinstance(data, bpy.types.Camera):
                    bpy.data.cameras.remove(data)
            for mesh in meshes:
                bpy.data.meshes.remove(mesh)
            bpy.data.scenes.remove(probe)
            shutil.rmtree(folder, ignore_errors=True)
        return compare(trees, seen)

    def row(self):
        widths = [2.0 * radius for _, radius, _ in self.spheres]
        offsets = numpy.cumsum([0.0] + widths[:-1]) + numpy.array(widths) / 2.0 - sum(widths) / 2.0
        return offsets, sum(widths)

    def prepare(self, probe, toward, distance, made):
        probe.render.engine = "CYCLES"
        probe.cycles.device = "CPU"
        probe.cycles.samples = CALIBRATION_SAMPLES
        probe.cycles.use_denoising = False
        probe.cycles.use_adaptive_sampling = False
        probe.cycles.seed = 0
        probe.cycles.transparent_max_bounces = 128
        probe.render.film_transparent = True
        probe.render.resolution_x = self.pixels * len(self.collections)
        probe.render.resolution_y = self.pixels
        probe.render.resolution_percentage = 100
        probe.render.use_compositing = False
        probe.render.image_settings.file_format = "OPEN_EXR"
        probe.render.image_settings.color_depth = "32"
        probe.render.image_settings.color_mode = "RGBA"
        probe.world = self.scene.world
        for light in (obj for obj in self.scene.objects if obj.type == "LIGHT" and not obj.hide_render):
            probe.collection.objects.link(light)
        right = numpy.cross(toward, [0.0, 0.0, 1.0])
        right = right / max(numpy.linalg.norm(right), 1e-9)
        offsets, width = self.row()
        for index, collection in enumerate(self.collections):
            empty = bpy.data.objects.new(f"calibration tree {index}", None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = collection
            empty.location = tuple(right * offsets[index])
            probe.collection.objects.link(empty)
            made.append(empty)
        height = max(height for _, _, height in self.spheres)
        aim = numpy.array([0.0, 0.0, height / 2.0])
        data = bpy.data.cameras.new("calibration camera")
        data.type = "ORTHO"
        data.ortho_scale = max(width, height) * 1.1
        data.clip_end = 4.0 * distance + 10.0 * width
        camera = bpy.data.objects.new("calibration camera", data)
        eye = aim - numpy.asarray(toward) * distance
        camera.matrix_world = Matrix.Translation(Vector(eye)) @ Vector(tuple(toward)).to_track_quat("-Z", "Y").to_matrix().to_4x4()
        probe.collection.objects.link(camera)
        probe.camera = camera
        made.append(camera)
        self.eye = eye

    def cards(self, probe, material, toward, distance, made, meshes):
        right = numpy.cross(toward, [0.0, 0.0, 1.0])
        right = right / max(numpy.linalg.norm(right), 1e-9)
        offsets, _ = self.row()
        trees = {"pivot": [], "turn": [], "view": [], "half": [], "variant": []}
        for index, (centre, radius, _) in enumerate(self.spheres):
            pivot = right * offsets[index] + numpy.asarray(centre)
            trees["pivot"].append(pivot)
            trees["turn"].append(0.0)
            trees["view"].append(impostors.local_view(pivot, 0.0, pivot - numpy.asarray(toward) * distance))
            trees["half"].append(radius * impostors.CELL_MARGIN)
            trees["variant"].append(index)
        mesh = card_mesh("calibration cards", trees, self.frames, len(self.collections))
        mesh.materials.append(material)
        meshes.append(mesh)
        obj = bpy.data.objects.new("calibration cards", mesh)
        probe.collection.objects.link(obj)
        made.append(obj)

    def render(self, probe, folder, name):
        path = os.path.join(folder, name + ".exr")
        probe.render.filepath = path
        bpy.ops.render.render(write_still=True, scene=probe.name)
        if not os.path.isfile(path):
            raise failed("the forest calibration wrote no image")
        image = exr_read.read_exr(path)
        prefix = next(prefix for prefix in ("", "ViewLayer.Combined.", "Combined.") if image.has(prefix + "R"))
        return numpy.asarray(image.stack(prefix, "RGBA"), dtype=numpy.float64)


def compare(trees, cards):
    """Gain per channel that makes the cards' mean colour that of the trees, the luminance step left before the gain,
    and the silhouette IoU over pixel coverage (sum of the smaller coverage over sum of the larger), which counts a
pixel half covered by thin twigs as half."""
    tree_cover, card_cover = numpy.clip(trees[..., 3], 0.0, 1.0), numpy.clip(cards[..., 3], 0.0, 1.0)
    iou = float(numpy.minimum(tree_cover, card_cover).sum()) / max(float(numpy.maximum(tree_cover, card_cover).sum()), 1e-9)
    tree_mean = trees[..., :3].sum(axis=(0, 1)) / max(float(trees[..., 3].sum()), 1e-9)
    card_mean = cards[..., :3].sum(axis=(0, 1)) / max(float(cards[..., 3].sum()), 1e-9)
    gain = numpy.clip(tree_mean / numpy.maximum(card_mean, 1e-6), *GAIN_RANGE)
    step = abs(float(card_mean @ LUMINANCE) / max(float(tree_mean @ LUMINANCE), 1e-9) - 1.0)
    return {"gain": [round(float(value), 4) for value in gain], "iou": round(iou, 4), "step_before": round(step, 4),
            "tree_colour": [round(float(v), 5) for v in tree_mean], "card_colour": [round(float(v), 5) for v in card_mean]}
