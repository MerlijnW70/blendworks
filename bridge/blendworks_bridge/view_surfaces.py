import bpy

from .rig import TEMPORARY_PREFIX
from .view_materials import group_material

PASSING = {"ShaderNodeBsdfTransparent", "ShaderNodeHoldout", "ShaderNodeBsdfRayPortal"}
SURFACE_TYPES = ("MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD")
ALPHA = "Alpha"


def surface_output(tree):
    output = tree.get_output_node("CYCLES")
    if output is None or output.bl_idname != "ShaderNodeOutputMaterial":
        return None
    return output


def volume_only(material):
    """A material that describes a volume and no surface: fog, haze or a cloud. Views leave it as it is."""
    tree = material.node_tree
    output = None if tree is None else surface_output(tree)
    return output is not None and output.inputs["Volume"].is_linked and not output.inputs["Surface"].is_linked


class Rewriter:
    """Puts the view's shader group in place of every closure that scatters or emits light (and of a colour linked straight
    into a shader socket, which renders as emission), in a copy of a material's tree.

    Transparent, holdout and ray portal closures stay, and so do the mix and add shaders between closures with their
    factors, so a surface keeps its opacity: an alpha mask still cuts a leaf card, and a surface that only casts shadows
    still casts the same shadows. A Principled BSDF's alpha becomes a mix with a transparent closure."""

    def __init__(self, group, groups):
        self.group = group
        self.groups = groups
        self.replaced = 0

    def view_node(self, tree):
        node = tree.nodes.new("ShaderNodeGroup")
        node.node_tree = self.group
        return node.outputs[0]

    def rewrite(self, tree, socket, seen=None):
        seen = set() if seen is None else seen
        if not socket.is_linked:
            return
        link = socket.links[0]
        node, source = link.from_node, link.from_socket
        key = (node.name, source.identifier, socket.node.name, socket.identifier)
        if key in seen:
            return
        seen.add(key)
        kind = node.bl_idname
        if kind == "NodeReroute":
            self.rewrite(tree, node.inputs[0], seen)
        elif kind in ("ShaderNodeMixShader", "ShaderNodeAddShader"):
            for entry in node.inputs:
                if entry.type == "SHADER":
                    self.rewrite(tree, entry, seen)
        elif kind == "ShaderNodeGroup":
            self.rewrite_group(node, source)
        elif kind in PASSING:
            return
        else:
            tree.links.new(self.closure(tree, node), socket)
            self.replaced += 1

    def closure(self, tree, node):
        view = self.view_node(tree)
        alpha = node.inputs.get(ALPHA) if node.bl_idname == "ShaderNodeBsdfPrincipled" else None
        if alpha is None or (not alpha.is_linked and alpha.default_value >= 1.0):
            return view
        mix = tree.nodes.new("ShaderNodeMixShader")
        if alpha.is_linked:
            tree.links.new(alpha.links[0].from_socket, mix.inputs[0])
        else:
            mix.inputs[0].default_value = alpha.default_value
        transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
        tree.links.new(transparent.outputs[0], mix.inputs[1])
        tree.links.new(view, mix.inputs[2])
        return mix.outputs[0]

    def rewrite_group(self, node, source):
        if node.node_tree is None:
            return
        copy = node.node_tree.copy()
        copy.name = TEMPORARY_PREFIX + "view_" + node.node_tree.name
        self.groups.append(copy)
        node.node_tree = copy
        outputs = [entry for entry in copy.nodes if entry.bl_idname == "NodeGroupOutput" and entry.is_active_output]
        for output in outputs:
            for entry in output.inputs:
                if entry.identifier == source.identifier:
                    self.rewrite(copy, entry)


class SurfaceSwap:
    """Gives every surface the view's shader for one render and takes it back: each used material is swapped for a copy whose
    light-scattering closures are the view's group, and empty material slots get the group alone."""

    def __init__(self, group, name):
        self.group = group
        self.name = name
        self.swapped = []
        self.groups = []
        self.filled = []
        self.material = None

    def apply(self, objects):
        for material in [material for material in bpy.data.materials if self.needs_view(material)]:
            copy = self.view_copy(material)
            material.user_remap(copy)
            self.swapped.append((material, copy))
        for obj in objects:
            self.fill(obj)
        return len(self.swapped)

    def needs_view(self, material):
        return material.users > int(material.use_fake_user) and not material.is_grease_pencil and not material.name.startswith(TEMPORARY_PREFIX) and not volume_only(material)

    def view_copy(self, material):
        copy = material.copy()
        copy.name = TEMPORARY_PREFIX + "view_" + material.name
        tree = copy.node_tree
        output = None if tree is None else surface_output(tree)
        if output is None:
            if tree is None:
                copy.use_nodes = True
                tree = copy.node_tree
            tree.nodes.clear()
            output = tree.nodes.new("ShaderNodeOutputMaterial")
        rewriter = Rewriter(self.group, self.groups)
        surface = output.inputs["Surface"]
        if surface.is_linked:
            rewriter.rewrite(tree, surface)
        else:
            tree.links.new(rewriter.view_node(tree), surface)
            rewriter.replaced += 1
        volume = output.inputs["Volume"]
        if rewriter.replaced and volume.is_linked:
            tree.links.remove(volume.links[0])
        return copy

    def view_material(self):
        if self.material is None:
            self.material = group_material(self.name, self.group)
        return self.material

    def fill(self, obj):
        if obj.type not in SURFACE_TYPES or obj.library is not None or obj.data is None or obj.data.library is not None:
            return
        if not obj.material_slots:
            materials = obj.data.materials
            if len(materials) == 0:
                materials.append(self.view_material())
                self.filled.append(materials.clear)
            return
        for index, slot in enumerate(obj.material_slots):
            if slot.material is None:
                slot.material = self.view_material()
                self.filled.append(lambda obj=obj, index=index: setattr(obj.material_slots[index], "material", None))

    def restore_steps(self):
        """Each step of taking the view back, in order, for the caller to run one by one."""
        steps = [step for step in reversed(self.filled)]
        steps += [lambda original=original, copy=copy: copy.user_remap(original) for original, copy in reversed(self.swapped)]
        steps += [lambda copy=copy: bpy.data.materials.remove(copy) for _, copy in reversed(self.swapped)]
        steps += [lambda group=group: bpy.data.node_groups.remove(group) for group in reversed(self.groups)]
        steps.append(self.remove_material)
        self.filled, self.swapped, self.groups = [], [], []
        return steps

    def remove_material(self):
        if self.material is not None:
            bpy.data.materials.remove(self.material)
            self.material = None
