import colorsys
import math

import bpy
from mathutils import Matrix, Vector

from .errors import bad_args
from .limits import MAX_LISTED_NAMES, MAX_WIRE_EDGES
from .rig import LENS, SENSOR, TEMPORARY_PREFIX, VIEW_DIRECTIONS

SHADINGS = ("shaded", "clay", "wireframe", "normals", "uv_checker", "material_id")
DIRECTIONS = dict(VIEW_DIRECTIONS, bottom=Vector((0.0, 0.0, -1.0)))
WIRE_PROPERTY = "blendworks_wire"
CLAY = (0.62, 0.62, 0.6, 1.0)
LINE = (0.02, 0.02, 0.025, 1.0)
GOLDEN = 0.618033988749895
FLAT_SHADINGS = ("normals", "uv_checker", "material_id")


def half_angle():
    return math.atan(SENSOR / 2.0 / LENS)


def aim(camera, centre, direction, distance):
    direction = Vector(direction).normalized()
    location = centre + direction * distance
    if direction.z > 0.999:
        rotation = Matrix.Identity(4)
    elif direction.z < -0.999:
        rotation = Matrix.Rotation(math.pi, 4, "X")
    else:
        rotation = (-direction).to_track_quat("-Z", "Y").to_matrix().to_4x4()
    camera.matrix_world = Matrix.Translation(location) @ rotation


def frame_width(camera_data, width, reach):
    distance = width / 2.0 / math.tan(half_angle())
    camera_data.clip_start = max(0.0005, distance * 0.02)
    camera_data.clip_end = distance + max(reach, width) * 8.0 + 1.0
    return distance


def pixel_size(distance, resolution):
    return 2.0 * distance * math.tan(half_angle()) / resolution


def temporary_material(name):
    material = bpy.data.materials.new(TEMPORARY_PREFIX + name)
    if not material.node_tree:
        material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    return material, nodes, material.node_tree.links, output


def emission_material(name, color):
    material, nodes, links, output = temporary_material(name)
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def clay_material(with_lines):
    material, nodes, links, output = temporary_material("clay")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.65
    if with_lines:
        attribute = nodes.new("ShaderNodeAttribute")
        attribute.attribute_type = "OBJECT"
        attribute.attribute_name = WIRE_PROPERTY
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = CLAY
        mix.inputs["B"].default_value = LINE
        links.new(attribute.outputs["Fac"], mix.inputs["Factor"])
        links.new(mix.outputs["Result"], shader.inputs["Base Color"])
    else:
        shader.inputs["Base Color"].default_value = CLAY
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def normals_material():
    material, nodes, links, output = temporary_material("normals")
    geometry = nodes.new("ShaderNodeNewGeometry")
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY_ADD"
    scale.inputs[1].default_value = (0.5, 0.5, 0.5)
    scale.inputs[2].default_value = (0.5, 0.5, 0.5)
    emission = nodes.new("ShaderNodeEmission")
    links.new(geometry.outputs["Normal"], scale.inputs[0])
    links.new(scale.outputs["Vector"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def checker_material(image):
    material, nodes, links, output = temporary_material("uv_checker")
    coordinates = nodes.new("ShaderNodeTexCoord")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.interpolation = "Linear"
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.8
    links.new(coordinates.outputs["UV"], texture.inputs["Vector"])
    links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def id_color(index):
    red, green, blue = colorsys.hsv_to_rgb((index * GOLDEN) % 1.0, 0.65, 0.9)
    return (red, green, blue, 1.0)


def hex_color(color):
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in color[:3])


def wire_tree():
    tree = bpy.data.node_groups.new(TEMPORARY_PREFIX + "wire", "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = tree.interface.new_socket("Source", in_out="INPUT", socket_type="NodeSocketObject")
    radius = tree.interface.new_socket("Radius", in_out="INPUT", socket_type="NodeSocketFloat")
    nodes = tree.nodes
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    info = nodes.new("GeometryNodeObjectInfo")
    info.transform_space = "RELATIVE"
    to_curve = nodes.new("GeometryNodeMeshToCurve")
    profile = nodes.new("GeometryNodeCurvePrimitiveCircle")
    profile.inputs["Resolution"].default_value = 4
    to_mesh = nodes.new("GeometryNodeCurveToMesh")
    links = tree.links
    links.new(group_in.outputs["Source"], info.inputs["Object"])
    links.new(group_in.outputs["Radius"], profile.inputs["Radius"])
    links.new(info.outputs["Geometry"], to_curve.inputs["Mesh"])
    links.new(to_curve.outputs["Curve"], to_mesh.inputs["Curve"])
    links.new(profile.outputs["Curve"], to_mesh.inputs["Profile Curve"])
    links.new(to_mesh.outputs["Mesh"], group_out.inputs["Geometry"])
    return tree, source.identifier, radius.identifier


class Shading:
    def __init__(self, scene, view_layer, mode):
        self.scene = scene
        self.view_layer = view_layer
        self.mode = mode
        self.override = view_layer.material_override
        view = scene.view_settings
        self.view = (view.view_transform, view.look, view.exposure, view.gamma)
        self.blocks = []
        self.remapped = []
        self.report = {}

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        self.restore()
        return False

    def keep(self, collection, block):
        self.blocks.append((collection, block))
        return block

    def apply(self, objects, wire_radius):
        mode = self.mode
        if mode in FLAT_SHADINGS:
            view = self.scene.view_settings
            view.view_transform = "Standard"
            view.look = "None"
            view.exposure = 0.0
            view.gamma = 1.0
        if mode in ("clay", "wireframe"):
            material = self.keep(bpy.data.materials, clay_material(mode == "wireframe"))
            self.view_layer.material_override = material
        if mode == "wireframe":
            self.add_wires(objects, wire_radius)
        elif mode == "normals":
            self.view_layer.material_override = self.keep(bpy.data.materials, normals_material())
        elif mode == "uv_checker":
            self.apply_checker(objects)
        elif mode == "material_id":
            self.apply_material_ids(objects)

    def apply_checker(self, objects):
        image = self.keep(bpy.data.images, bpy.data.images.new(TEMPORARY_PREFIX + "checker", 1024, 1024))
        image.generated_type = "COLOR_GRID"
        self.view_layer.material_override = self.keep(bpy.data.materials, checker_material(image))
        missing = sorted(obj.name for obj in objects if obj.type == "MESH" and len(obj.data.uv_layers) == 0)
        self.report["objects_without_uv"] = missing[:MAX_LISTED_NAMES]

    def apply_material_ids(self, objects):
        used = sorted({slot.material for obj in objects for slot in obj.material_slots if slot.material is not None}, key=lambda m: m.name)
        legend = {}
        for index, material in enumerate(used):
            color = id_color(index)
            flat = self.keep(bpy.data.materials, emission_material(f"id_{index}", color))
            material.user_remap(flat)
            self.remapped.append((flat, material))
            legend[material.name] = hex_color(color)
        self.report["material_colors"] = legend

    def add_wires(self, objects, radius):
        meshes = [obj for obj in objects if obj.type in ("MESH", "CURVE", "FONT", "SURFACE", "META")]
        edges = sum(len(obj.data.edges) for obj in meshes if obj.type == "MESH")
        if edges > MAX_WIRE_EDGES:
            raise bad_args(f"wireframe draws at most {MAX_WIRE_EDGES} edges and the scene has {edges}; use clay, or focus on fewer objects")
        tree, source, size = wire_tree()
        self.keep(bpy.data.node_groups, tree)
        for obj in meshes:
            holder = self.keep(bpy.data.meshes, bpy.data.meshes.new(TEMPORARY_PREFIX + "wire"))
            wire = self.keep(bpy.data.objects, bpy.data.objects.new(TEMPORARY_PREFIX + "wire", holder))
            self.scene.collection.objects.link(wire)
            wire[WIRE_PROPERTY] = 1.0
            modifier = wire.modifiers.new("wire", "NODES")
            modifier.node_group = tree
            inputs = modifier.properties.inputs
            getattr(inputs, source).value = obj
            getattr(inputs, size).value = radius
        self.report["wire_edges"] = edges

    def restore(self):
        for flat, material in reversed(self.remapped):
            flat.user_remap(material)
        self.remapped = []
        self.view_layer.material_override = self.override
        view = self.scene.view_settings
        view.view_transform, view.look, view.exposure, view.gamma = self.view
        for collection, block in reversed(self.blocks):
            collection.remove(block, do_unlink=True)
        self.blocks = []
