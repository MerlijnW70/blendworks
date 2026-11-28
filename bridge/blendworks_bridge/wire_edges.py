"""Wire edge node group builder."""

import bpy

from .rig import TEMPORARY_PREFIX
from .view_materials import CORNER_ATTRIBUTE, EDGE_ATTRIBUTES, OUTSIDE_EDGE
from .view_surfaces import volume_only

MODIFIER = "bw_wire_edges"
GROUP_NAME = TEMPORARY_PREFIX + "wire_edges"


class Builder:
    def __init__(self, tree):
        self.nodes = tree.nodes
        self.links = tree.links

    def math(self, operation, a, b=None, clamp=False, epsilon=None):
        node = self.nodes.new("ShaderNodeMath")
        node.operation = operation
        node.use_clamp = clamp
        self.set(node, 0, a)
        if b is not None:
            self.set(node, 1, b)
        if epsilon is not None:
            node.inputs[2].default_value = epsilon
        return node.outputs[0]

    def vector(self, operation, a, b=None):
        node = self.nodes.new("ShaderNodeVectorMath")
        node.operation = operation
        self.set(node, 0, a)
        if b is not None:
            self.set(node, 1, b)
        return node.outputs["Value" if operation in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else "Vector"]

    def set(self, node, index, value):
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value if node.bl_idname == "ShaderNodeMath" else (value, value, value)
        else:
            self.links.new(value, node.inputs[index])

    def socket(self, node, name, data_type):
        wanted = {"FLOAT": "VALUE", "FLOAT_VECTOR": "VECTOR", "INT": "INT"}[data_type]
        for socket in node.inputs:
            if socket.name == name and socket.type == wanted:
                return socket
        raise KeyError(name)

    def sample(self, geometry, domain, data_type, value, index):
        node = self.nodes.new("GeometryNodeSampleIndex")
        node.domain = domain
        node.data_type = data_type
        self.links.new(geometry, node.inputs["Geometry"])
        self.links.new(value, self.socket(node, "Value", data_type))
        self.links.new(index, node.inputs["Index"])
        return node.outputs["Value"] if data_type == "FLOAT" else [s for s in node.outputs if s.name == "Value" and s.type == "VECTOR"][0]

    def at_index(self, domain, data_type, value, index):
        node = self.nodes.new("GeometryNodeFieldAtIndex")
        node.domain = domain
        node.data_type = data_type
        self.links.new(index, node.inputs["Index"])
        self.links.new(value, self.socket(node, "Value", data_type))
        return node.outputs["Value"]


def corner_offset(build, corner, offset):
    node = build.nodes.new("GeometryNodeOffsetCornerInFace")
    build.links.new(corner, node.inputs["Corner Index"])
    node.inputs["Offset"].default_value = offset
    return node.outputs["Corner Index"]


def face_corner(build, sort_index, face=None):
    node = build.nodes.new("GeometryNodeCornersOfFace")
    if face is not None:
        build.links.new(face, node.inputs["Face Index"])
    node.inputs["Sort Index"].default_value = sort_index
    return node.outputs["Corner Index"]


def corner_position(build, geometry, corner):
    vertex = build.nodes.new("GeometryNodeVertexOfCorner")
    build.links.new(corner, vertex.inputs["Corner Index"])
    position = build.nodes.new("GeometryNodeInputPosition")
    return build.sample(geometry, "POINT", "FLOAT_VECTOR", position.outputs["Position"], vertex.outputs["Vertex Index"])


def store(build, geometry, domain, name, value):
    node = build.nodes.new("GeometryNodeStoreNamedAttribute")
    node.domain = domain
    node.data_type = "FLOAT_VECTOR"
    node.inputs["Name"].default_value = name
    build.links.new(geometry, node.inputs["Geometry"])
    build.links.new(value, build.socket(node, "Value", "FLOAT_VECTOR"))
    return node.outputs["Geometry"]


def combine(build, values):
    node = build.nodes.new("ShaderNodeCombineXYZ")
    for socket, value in zip(node.inputs, values):
        build.links.new(value, socket)
    return node.outputs[0]


def build_group():
    """Triangulates as the renderer would and stores, in object space, what the wire shader needs:

    - per corner, its barycentric weight for each of the triangle's three corners, plus OUTSIDE_EDGE on the weight whose
      opposite edge the triangulation cut (a quad's diagonal), so that edge is never the nearest;
    - per triangle, the vectors from its first corner to its second and its third."""
    tree = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    build = Builder(tree)
    nodes, links = build.nodes, build.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    size = nodes.new("GeometryNodeAttributeDomainSize")
    size.component = "MESH"
    links.new(group_in.outputs["Geometry"], size.inputs["Geometry"])
    triangulate = nodes.new("GeometryNodeTriangulate")
    links.new(group_in.outputs["Geometry"], triangulate.inputs["Mesh"])
    geometry = triangulate.outputs["Mesh"]

    index = nodes.new("GeometryNodeInputIndex").outputs["Index"]
    edges = nodes.new("GeometryNodeEdgesOfCorner")
    links.new(corner_offset(build, index, 1), edges.inputs["Corner Index"])
    opposite_real = build.math("LESS_THAN", edges.outputs["Next Edge Index"], build.math("SUBTRACT", size.outputs["Edge Count"], 0.5))
    cut = build.math("SUBTRACT", 1.0, opposite_real)
    face = nodes.new("GeometryNodeFaceOfCorner")
    links.new(index, face.inputs["Corner Index"])
    weights = []
    for number in range(3):
        mine = build.math("COMPARE", face.outputs["Index in Face"], float(number), epsilon=0.1)
        corner = face_corner(build, number, face.outputs["Face Index"])
        far = build.at_index("CORNER", "FLOAT", cut, corner)
        weights.append(build.math("ADD", mine, build.math("MULTIPLY", far, OUTSIDE_EDGE)))
    geometry = store(build, geometry, "CORNER", CORNER_ATTRIBUTE, combine(build, weights))

    first = corner_position(build, geometry, face_corner(build, 0))
    for number, name in zip((1, 2), EDGE_ATTRIBUTES):
        other = corner_position(build, geometry, face_corner(build, number))
        geometry = store(build, geometry, "FACE", name, build.vector("SUBTRACT", other, first))
    links.new(geometry, group_out.inputs["Geometry"])
    return tree


def describes_no_surface(obj):
    """An object whose every material is a volume with no surface (a fog box, a cloud): it has no edges to draw."""
    materials = [slot.material for slot in obj.material_slots if slot.material is not None]
    return bool(materials) and all(volume_only(material) for material in materials)


def has_edges_to_draw(obj):
    return obj.type == "MESH" and obj.library is None and obj.data.library is None and not describes_no_surface(obj)


def shares_its_mesh(obj):
    """An object whose evaluated mesh is its mesh data: no modifiers and no shape keys."""
    return len(obj.modifiers) == 0 and obj.data.shape_keys is None


class PolygonEdges:
    """Edge attributes for one render, on every mesh that draws edges.

    - A mesh with modifiers or shape keys gets them from a last Geometry Nodes modifier, after everything else, so they
      describe the mesh the render sees; its evaluated mesh is its own in any case.
    - A plain mesh datablock is evaluated once into a temporary mesh with the attributes, which every object using that
      datablock shows for the render: linked copies stay instances of one mesh, and memory grows with the distinct meshes,
      not with the copies."""

    def __init__(self):
        self.tree = None
        self.added = []
        self.swapped = []
        self.meshes = []

    def group(self):
        if self.tree is None:
            self.tree = build_group()
        return self.tree

    def attach(self, objects, scene, view_layer):
        users = {}
        for obj in objects:
            if not has_edges_to_draw(obj):
                continue
            if shares_its_mesh(obj):
                users.setdefault(obj.data, []).append(obj)
                continue
            active = obj.modifiers.active.name if obj.modifiers.active is not None else None
            modifier = obj.modifiers.new(MODIFIER, "NODES")
            self.added.append((obj, modifier, active))
            modifier.node_group = self.group()
        meshes = list(users)
        for mesh, copy in zip(meshes, self.evaluated(meshes, scene, view_layer)):
            for obj in users[mesh]:
                self.swapped.append((obj, mesh, obj.active_material_index))
                obj.data = copy
        return len(self.added) + len(self.swapped)

    def evaluated(self, meshes, scene, view_layer):
        holders = []
        try:
            for mesh in meshes:
                holder = bpy.data.objects.new(TEMPORARY_PREFIX + "wire_source", mesh)
                holders.append(holder)
                scene.collection.objects.link(holder)
                holder.modifiers.new(MODIFIER, "NODES").node_group = self.group()
            if not holders:
                return []
            view_layer.update()
            depsgraph = view_layer.depsgraph
            copies = []
            for mesh, holder in zip(meshes, holders):
                copy = bpy.data.meshes.new_from_object(holder.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
                self.meshes.append(copy)
                copy.name = TEMPORARY_PREFIX + "wire_" + mesh.name
                copy.materials.clear()
                for material in mesh.materials:
                    copy.materials.append(material)
                copies.append(copy)
            return copies
        finally:
            for holder in holders:
                bpy.data.objects.remove(holder)

    def restore_steps(self):
        """Each step of taking the attributes away, in order, for the caller to run one by one."""
        steps = [lambda obj=obj, modifier=modifier: obj.modifiers.remove(modifier) for obj, modifier, _ in reversed(self.added)]
        steps += [lambda obj=obj, active=active: setattr(obj.modifiers, "active", obj.modifiers[active])
                  for obj, _, active in self.added if active is not None]
        steps += [lambda obj=obj, mesh=mesh, index=index: (setattr(obj, "data", mesh), setattr(obj, "active_material_index", index))
                  for obj, mesh, index in reversed(self.swapped)]
        steps += [lambda mesh=mesh: bpy.data.meshes.remove(mesh) for mesh in reversed(self.meshes)]
        steps.append(self.remove_group)
        self.added, self.swapped, self.meshes = [], [], []
        return steps

    def remove_group(self):
        if self.tree is not None:
            bpy.data.node_groups.remove(self.tree)
            self.tree = None
