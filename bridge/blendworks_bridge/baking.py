import bpy

from .errors import bad_args, failed
from .operators import only_selected, operator_context
from .procedural import surface_principled

CHANNELS = ("base_color", "roughness", "metallic", "emission", "normal", "ao")
COLOR_CHANNELS = ("base_color", "emission")
EMISSION_SOURCES = {"base_color": "Base Color", "roughness": "Roughness", "metallic": "Metallic", "emission": "Emission Color"}
DEFAULT_SAMPLES = {"base_color": 4, "roughness": 4, "metallic": 4, "emission": 4, "normal": 8, "ao": 64}
BACKGROUNDS = {
    "base_color": (0.0, 0.0, 0.0, 1.0),
    "roughness": (0.5, 0.5, 0.5, 1.0),
    "metallic": (0.0, 0.0, 0.0, 1.0),
    "emission": (0.0, 0.0, 0.0, 1.0),
    "normal": (0.5, 0.5, 1.0, 1.0),
    "ao": (1.0, 1.0, 1.0, 1.0),
}
TEMPORARY_MATERIAL = "blendworks_bake_target"
TEMPORARY_WORLD = "blendworks_bake_world"


class SceneSettings:
    def __init__(self, scene):
        self.scene = scene
        cycles = scene.cycles
        bake = scene.render.bake
        self.saved = [(scene.render, "engine", scene.render.engine)]
        for owner, names in (
            (cycles, ("samples", "use_adaptive_sampling", "use_denoising", "seed", "use_animated_seed")),
            (bake, ("margin", "margin_type", "use_selected_to_active", "cage_extrusion", "max_ray_distance", "normal_space", "use_clear", "target", "use_cage")),
        ):
            for name in names:
                self.saved.append((owner, name, getattr(owner, name)))
        self.world = scene.world
        self.distance = scene.world.light_settings.distance if scene.world is not None else None

    def prepare(self, ao_distance):
        scene = self.scene
        scene.render.engine = "CYCLES"
        scene.cycles.use_adaptive_sampling = False
        scene.cycles.use_denoising = False
        scene.cycles.seed = 0
        scene.cycles.use_animated_seed = False
        if ao_distance is not None:
            if scene.world is None:
                scene.world = bpy.data.worlds.new(TEMPORARY_WORLD)
            scene.world.light_settings.distance = ao_distance

    def restore(self):
        for owner, name, value in self.saved:
            setattr(owner, name, value)
        scene = self.scene
        if scene.world is not None and scene.world != self.world:
            temporary = scene.world
            scene.world = self.world
            bpy.data.worlds.remove(temporary)
        if self.world is not None and self.distance is not None:
            self.world.light_settings.distance = self.distance


def shading_materials(objects, what):
    found = []
    for obj in objects:
        slots = [slot.material for slot in obj.material_slots]
        if not slots or any(material is None for material in slots):
            raise bad_args(f"{obj.name} needs a material in every slot to bake {what}")
        for material in slots:
            if material not in found:
                found.append(material)
    return found


class EmissionSwap:
    def __init__(self, materials):
        self.materials = materials
        self.added = []
        self.surfaces = []
        self.strength = None

    def check(self):
        strengths = set()
        for material in self.materials:
            _, shader = surface_principled(material)
            socket = shader.inputs["Emission Strength"]
            strengths.add(None if socket.is_linked else round(socket.default_value, 6))
        if len(strengths) == 1 and None not in strengths:
            self.strength = strengths.pop()

    def apply(self, channel):
        for material in self.materials:
            output, shader = surface_principled(material)
            tree = material.node_tree
            emission = tree.nodes.new("ShaderNodeEmission")
            self.added.append((tree, emission))
            self.surfaces.append((tree, output, output.inputs["Surface"].links[0].from_socket))
            feed(tree, shader.inputs[EMISSION_SOURCES[channel]], emission.inputs["Color"])
            emission.inputs["Strength"].default_value = 1.0
            if channel == "emission" and self.strength is None:
                feed_value(tree, shader.inputs["Emission Strength"], emission.inputs["Strength"])
            tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    def restore(self):
        for tree, output, source in reversed(self.surfaces):
            tree.links.new(source, output.inputs["Surface"])
        for tree, node in reversed(self.added):
            tree.nodes.remove(node)
        self.surfaces = []
        self.added = []


def feed_value(tree, socket, target):
    if socket.is_linked:
        tree.links.new(socket.links[0].from_socket, target)
    else:
        target.default_value = socket.default_value


def feed(tree, socket, target):
    if socket.is_linked:
        tree.links.new(socket.links[0].from_socket, target)
        return
    value = socket.default_value
    if isinstance(value, float):
        target.default_value = (value, value, value, 1.0)
    else:
        target.default_value = list(value)[:3] + [1.0]


class TargetNodes:
    def __init__(self, ctx, targets):
        self.ctx = ctx
        self.targets = targets
        self.temporary = None
        self.padded = []
        self.nodes = []
        self.found = []

    def prepare(self):
        found = []
        for obj in self.targets:
            slots = [slot.material for slot in obj.material_slots]
            if any(material is None for material in slots):
                raise bad_args(f"{obj.name} has an empty material slot; fill or remove it before baking")
            if not slots:
                self.ctx.txn.touch_mesh(obj.data)
                if self.temporary is None:
                    self.temporary = bpy.data.materials.new(TEMPORARY_MATERIAL)
                obj.data.materials.append(self.temporary)
                self.padded.append(obj)
                slots = [self.temporary]
            for material in slots:
                if material not in found:
                    found.append(material)
        self.found = found
        return found

    def point_at(self, image):
        self.clear()
        for material in self.found:
            tree = material.node_tree
            node = tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            self.nodes.append((tree, node, tree.nodes.active))
            tree.nodes.active = node

    def clear(self):
        for tree, node, previous in reversed(self.nodes):
            tree.nodes.remove(node)
            tree.nodes.active = previous
        self.nodes = []

    def remove(self):
        self.clear()
        for obj in self.padded:
            obj.data.materials.clear()
        self.padded = []
        if self.temporary is not None:
            bpy.data.materials.remove(self.temporary)
            self.temporary = None


def run_bake_operator(ctx, channel, active, objects, options):
    arguments = {
        "type": "EMIT" if channel in EMISSION_SOURCES else channel.upper(),
        "margin": options["margin"],
        "margin_type": "EXTEND",
        "use_selected_to_active": options["selected_to_active"],
        "cage_extrusion": options["cage_extrusion"],
        "max_ray_distance": options["max_ray_distance"],
        "normal_space": "TANGENT",
        "normal_r": "POS_X",
        "normal_g": "POS_Y",
        "normal_b": "POS_Z",
        "target": "IMAGE_TEXTURES",
        "use_clear": False,
        "use_cage": False,
        "uv_layer": options["uv_map"] or "",
    }
    with only_selected(ctx.view_layer, active, objects):
        with bpy.context.temp_override(**operator_context(active, objects)):
            outcome = bpy.ops.object.bake(**arguments)
    if "FINISHED" not in outcome:
        raise failed(f"baking {channel} was cancelled")


def bake_image(name, width, height, channel, float_buffer):
    data = channel not in COLOR_CHANNELS
    image = bpy.data.images.new(name, width, height, alpha=False, float_buffer=float_buffer and data)
    image.colorspace_settings.name = "Non-Color" if data else "sRGB"
    image.generated_color = BACKGROUNDS[channel]
    image.use_fake_user = True
    return image
