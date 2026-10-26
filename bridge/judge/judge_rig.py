from math import radians, sin, tan

import bpy
from mathutils import Matrix, Vector

RESOLUTION = 512
SAMPLES = 64
SEED = 0
BACKGROUND_GREY = 0.18
FIELD_OF_VIEW = radians(35.0)
FRAME_MARGIN = 1.18
MINIMUM_EXTENT = 1e-3

VIEWS = {
    "front": (Vector((0.0, -1.0, 0.0)), Vector((0.0, 0.0, 1.0)), True),
    "back": (Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0)), True),
    "left": (Vector((-1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), True),
    "right": (Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), True),
    "top": (Vector((0.0, 0.0, 1.0)), Vector((0.0, 1.0, 0.0)), True),
    "bottom": (Vector((0.0, 0.0, -1.0)), Vector((0.0, -1.0, 0.0)), True),
    "three-quarter": (Vector((1.0, -1.0, 0.8)).normalized(), Vector((0.0, 0.0, 1.0)), False),
}

LIGHTS = (
    ("key", Vector((0.9, 0.9, 1.0)), 3.0, 8.0),
    ("fill", Vector((-1.0, 0.1, 0.4)), 1.0, 20.0),
    ("rim", Vector((0.3, 1.0, -1.6)), 2.2, 6.0),
)


def basis(towards_viewer, up):
    depth = towards_viewer.normalized()
    side = up.cross(depth).normalized()
    upward = depth.cross(side).normalized()
    return side, upward, depth


def orientation(side, upward, depth):
    return Matrix((side, upward, depth)).transposed().to_4x4()


def configure_scene(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.seed = SEED
    scene.cycles.use_animated_seed = False
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.shading_system = False
    scene.render.resolution_x = RESOLUTION
    scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.dither_intensity = 0.0
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.frame_set(1)
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = 1.5
    settings = scene.view_layers[0].freestyle_settings
    for existing in list(settings.linesets):
        settings.linesets.remove(existing)
    line_set = settings.linesets.new("judge-lines")
    line_set.select_by_visibility = True
    line_set.select_silhouette = True
    line_set.select_border = True
    line_set.select_crease = True
    line_style = bpy.data.linestyles.new("judge-lines")
    line_style.color = (0.05, 0.05, 0.05)
    line_style.thickness = 1.5
    line_set.linestyle = line_style
    scene.world = studio_world()


def studio_world():
    world = bpy.data.worlds.new("judge-world")
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    seen_by_camera = nodes.new("ShaderNodeBackground")
    seen_by_camera.inputs["Color"].default_value = (BACKGROUND_GREY, BACKGROUND_GREY, BACKGROUND_GREY, 1.0)
    coordinates = nodes.new("ShaderNodeTexCoord")
    split = nodes.new("ShaderNodeSeparateXYZ")
    height = nodes.new("ShaderNodeMapRange")
    height.inputs["From Min"].default_value = -1.0
    height.inputs["From Max"].default_value = 1.0
    height.inputs["To Min"].default_value = 0.04
    height.inputs["To Max"].default_value = 0.55
    lighting = nodes.new("ShaderNodeBackground")
    path = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(coordinates.outputs["Generated"], split.inputs["Vector"])
    links.new(split.outputs["Z"], height.inputs["Value"])
    links.new(height.outputs["Result"], lighting.inputs["Color"])
    links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    links.new(lighting.outputs["Background"], mix.inputs[1])
    links.new(seen_by_camera.outputs["Background"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return world


def remove_foreign_rig(scene):
    for obj in list(scene.objects):
        if obj.type in {"LIGHT", "CAMERA", "LIGHT_PROBE"}:
            bpy.data.objects.remove(obj, do_unlink=True)


class Rig:
    def __init__(self, scene, low, high, origin):
        self.scene = scene
        self.low = Vector([min(low[axis], origin[axis]) for axis in range(3)])
        self.high = Vector([max(high[axis], origin[axis]) for axis in range(3)])
        self.centre = (self.low + self.high) / 2
        self.half = Vector([max((self.high[axis] - self.low[axis]) / 2, MINIMUM_EXTENT) for axis in range(3)])
        self.radius = self.half.length
        self.ortho_scale = 2.0 * max(self.half) * FRAME_MARGIN
        camera_data = bpy.data.cameras.new("judge-camera")
        self.camera = bpy.data.objects.new("judge-camera", camera_data)
        scene.collection.objects.link(self.camera)
        scene.camera = self.camera
        self.lights = []
        for name, direction, strength, angle in LIGHTS:
            light_data = bpy.data.lights.new(f"judge-{name}", "SUN")
            light_data.energy = strength
            light_data.angle = radians(angle)
            light = bpy.data.objects.new(f"judge-{name}", light_data)
            scene.collection.objects.link(light)
            self.lights.append((light, direction))

    def aim(self, view):
        towards_viewer, up, orthographic = VIEWS[view]
        side, upward, depth = basis(towards_viewer, up)
        camera = self.camera.data
        distance = self.radius * 4.0
        if orthographic:
            camera.type = "ORTHO"
            camera.ortho_scale = self.ortho_scale
        else:
            camera.type = "PERSP"
            camera.sensor_fit = "HORIZONTAL"
            camera.angle = FIELD_OF_VIEW
            distance = self.radius * FRAME_MARGIN / sin(FIELD_OF_VIEW / 2)
        camera.clip_start = max(distance - self.radius * 2.0, distance * 1e-3)
        camera.clip_end = distance + self.radius * 2.0
        self.camera.matrix_world = Matrix.Translation(self.centre + depth * distance) @ orientation(side, upward, depth)
        for light, direction in self.lights:
            towards_light = (side * direction.x + upward * direction.y + depth * direction.z).normalized()
            light_side, light_up, light_depth = basis(towards_light, upward if abs(towards_light.dot(upward)) < 0.99 else side)
            light.matrix_world = orientation(light_side, light_up, light_depth)
        bpy.context.view_layer.update()

    def tile_width(self, view):
        return self.ortho_scale if VIEWS[view][2] else None

    def project(self, point):
        camera = self.camera.data
        local = self.camera.matrix_world.inverted() @ Vector(point)
        if camera.type == "ORTHO":
            half = camera.ortho_scale / 2
            x = local.x / half
            y = local.y / half
        else:
            if local.z >= 0:
                return None, None
            half = tan(camera.angle / 2)
            x = (local.x / -local.z) / half
            y = (local.y / -local.z) / half
        return (x + 1) / 2 * RESOLUTION, (1 - (y + 1) / 2) * RESOLUTION

    def render(self, view, path):
        self.aim(view)
        self.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
