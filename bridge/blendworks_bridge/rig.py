import math

import bpy
from mathutils import Matrix, Vector

VIEW_DIRECTIONS = {
    "front": Vector((0.0, -1.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "left": Vector((-1.0, 0.0, 0.0)),
    "right": Vector((1.0, 0.0, 0.0)),
    "top": Vector((0.0, 0.0, 1.0)),
    "three-quarter": Vector((1.0, -1.0, 0.8)),
}

STUDIO_LIGHTS = (
    ("Key", Vector((0.6, 0.8, 1.0)), 3.0),
    ("Fill", Vector((-1.0, 0.1, 0.8)), 1.2),
    ("Rim", Vector((0.2, 1.0, -0.8)), 2.0),
)

LENS = 50.0
SENSOR = 36.0
TEMPORARY_PREFIX = "blendworks_preview_"


class PreviewRig:
    def __init__(self, scene):
        self.scene = scene
        self.objects = []
        self.data = []
        self.world = None
        self.camera = None
        self.lights = []

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        self.remove()
        return False

    def add_object(self, name, data):
        self.data.append(data)
        obj = bpy.data.objects.new(TEMPORARY_PREFIX + name, data)
        self.scene.collection.objects.link(obj)
        self.objects.append(obj)
        return obj

    def fitted_camera(self, bounds):
        data = bpy.data.cameras.new(TEMPORARY_PREFIX + "camera")
        data.lens = LENS
        data.sensor_width = SENSOR
        data.sensor_fit = "AUTO"
        self.camera = self.add_object("camera", data)
        self.centre, self.radius = sphere_of(bounds)
        half_angle = math.atan(SENSOR / 2.0 / LENS)
        self.distance = self.radius / math.sin(half_angle) * 1.08
        data.clip_start = max(0.001, (self.distance - self.radius) * 0.5)
        data.clip_end = self.distance + self.radius * 4.0 + 1.0
        return self.camera

    def point_camera(self, view):
        direction = VIEW_DIRECTIONS[view].normalized()
        location = self.centre + direction * self.distance
        if abs(direction.z) > 0.999:
            rotation = Matrix.Identity(4)
        else:
            rotation = (-direction).to_track_quat("-Z", "Y").to_matrix().to_4x4()
        self.camera.matrix_world = Matrix.Translation(location) @ rotation
        return self.camera

    def add_studio_lights(self):
        for name, direction, strength in STUDIO_LIGHTS:
            light = bpy.data.lights.new(TEMPORARY_PREFIX + name, "SUN")
            light.energy = strength
            light.angle = math.radians(10.0)
            self.lights.append((self.add_object(name, light), direction))
        self.light_from(Matrix.Identity(3))

    def light_from(self, camera_rotation):
        for obj, direction in self.lights:
            world_direction = camera_rotation @ direction.normalized()
            obj.matrix_world = world_direction.to_track_quat("Z", "Y").to_matrix().to_4x4()

    def add_grey_world(self):
        world = bpy.data.worlds.new(TEMPORARY_PREFIX + "world")
        world.color = (0.18, 0.18, 0.18)
        if world.node_tree is not None:
            for node in world.node_tree.nodes:
                if node.type == "BACKGROUND":
                    node.inputs["Color"].default_value = (0.18, 0.18, 0.18, 1.0)
                    node.inputs["Strength"].default_value = 1.0
        self.world = world
        self.scene.world = world

    def remove(self):
        for obj in self.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for data in self.data:
            if isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
            else:
                bpy.data.lights.remove(data)
        if self.world is not None:
            bpy.data.worlds.remove(self.world)
        self.objects = []
        self.data = []
        self.lights = []
        self.world = None


def sphere_of(bounds):
    if bounds is None:
        return Vector((0.0, 0.0, 0.0)), 1.0
    low, high = bounds
    centre = (low + high) / 2
    radius = max((high - low).length / 2, 0.01)
    return centre, radius


def stamp_fields(render):
    return [prop.identifier for prop in render.bl_rna.properties if prop.identifier.startswith("use_stamp")]


class RenderSettings:
    FIELDS = (
        ("render", ("engine", "resolution_x", "resolution_y", "resolution_percentage", "pixel_aspect_x",
                    "pixel_aspect_y", "filepath", "film_transparent", "use_border", "use_compositing",
                    "use_sequencer")),
        ("image", ("file_format", "color_mode", "color_depth", "compression")),
        ("cycles", ("device", "samples", "seed", "use_animated_seed", "use_denoising", "use_adaptive_sampling",
                    "preview_samples")),
        ("eevee", ("taa_render_samples",)),
    )

    def __init__(self, scene):
        self.scene = scene
        self.saved = []
        self.camera = scene.camera
        self.world = scene.world
        for group, names in self.FIELDS:
            owner = self.owner(group)
            if owner is None:
                continue
            for name in names:
                if hasattr(owner, name):
                    self.saved.append((owner, name, getattr(owner, name)))
        for name in stamp_fields(scene.render):
            self.saved.append((scene.render, name, getattr(scene.render, name)))

    def owner(self, group):
        scene = self.scene
        if group == "render":
            return scene.render
        if group == "image":
            return scene.render.image_settings
        return getattr(scene, group, None)

    def restore(self):
        for owner, name, value in self.saved:
            setattr(owner, name, value)
        self.scene.camera = self.camera
        self.scene.world = self.world
