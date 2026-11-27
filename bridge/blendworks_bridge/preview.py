import colorsys
import math

import bpy
from mathutils import Matrix, Vector

from . import render_view, view_materials
from .limits import MAX_LISTED_NAMES
from .rig import LENS, SENSOR, TEMPORARY_PREFIX, VIEW_DIRECTIONS

SHADINGS = ("shaded", "clay", "wireframe", "normals", "uv_checker", "material_id")
DIRECTIONS = dict(VIEW_DIRECTIONS, bottom=Vector((0.0, 0.0, -1.0)))
GOLDEN = 0.618033988749895
FLAT_SHADINGS = ("uv_checker", "material_id")


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


def emission_material(name, color):
    material, nodes, links, output = view_materials.temporary_material(name)
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def checker_material(image):
    material, nodes, links, output = view_materials.temporary_material("uv_checker")
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


class Shading:
    def __init__(self, scene, view_layer, mode, wire_width=view_materials.DEFAULT_WIRE_WIDTH, wire_triangles=False):
        self.scene = scene
        self.view_layer = view_layer
        self.mode = mode
        self.override = view_layer.material_override
        view = scene.view_settings
        self.view = (view.view_transform, view.look, view.exposure, view.gamma)
        self.blocks = []
        self.remapped = []
        self.report = {}
        self.surface = render_view.RenderView(scene, view_layer, mode, None, wire_width, wire_triangles) if mode in render_view.VIEWS else None

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        self.restore()
        return False

    def keep(self, collection, block):
        self.blocks.append((collection, block))
        return block

    def apply(self, objects, camera):
        mode = self.mode
        if mode in render_view.SURFACE_VIEWS:
            self.surface.camera = camera
            self.surface.apply(counted=objects)
            self.report.update(self.surface.report)
            return
        if mode in FLAT_SHADINGS:
            view = self.scene.view_settings
            view.view_transform = "Standard"
            view.look = "None"
            view.exposure = 0.0
            view.gamma = 1.0
        if mode == "uv_checker":
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

    def restore(self):
        """Puts the scene back; every step runs even when an earlier one fails."""
        steps = [self.surface.restore] if self.surface is not None else []
        steps += [lambda flat=flat, material=material: flat.user_remap(material) for flat, material in reversed(self.remapped)]
        steps += [self.restore_settings]
        steps += [lambda collection=collection, block=block: collection.remove(block, do_unlink=True) for collection, block in reversed(self.blocks)]
        self.remapped = []
        self.blocks = []
        render_view.run_all(steps)

    def restore_settings(self):
        self.view_layer.material_override = self.override
        view = self.scene.view_settings
        view.view_transform, view.look, view.exposure, view.gamma = self.view
