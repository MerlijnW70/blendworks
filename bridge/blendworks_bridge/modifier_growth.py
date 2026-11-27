"""Lower bounds on the vertex counts of the modifiers that multiply a mesh, known before Blender evaluates them."""
import bmesh
import numpy

from .errors import bad_args
from .limits import MAX_MESH_VERTICES

ADVICE = {"BEVEL": "Lower segments or bevel fewer edges (limit_method).", "SCREW": "Lower steps or iterations."}
AXES = {"X": 0, "Y": 1, "Z": 2}
ANGLE_MARGIN = 1e-4
MERGE_MARGIN = 1e-6


class InputShape:
    """The mesh a new modifier will receive: its vertices and, for bevel, the face angle at every edge."""

    def __init__(self, mesh, with_edges):
        self.vertices = len(mesh.vertices)
        points = numpy.empty(self.vertices * 3)
        mesh.vertices.foreach_get("co", points)
        self.points = points.reshape(-1, 3)
        self.edges = []
        self.corners = set()
        if not with_edges:
            return
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            self.edges = [(edge.calc_face_angle(None), edge.verts[0].index, edge.verts[1].index) for edge in bm.edges]
            self.corners = {vert.index for vert in bm.verts if len(vert.link_edges) >= 3 and all(edge.is_manifold for edge in vert.link_edges)}
        finally:
            bm.free()


def input_shape(ctx, obj, blender_type, apply):
    """None for modifiers that do not multiply the mesh; apply evaluates the new modifier on the bare mesh."""
    if blender_type not in ADVICE:
        return None
    with_edges = blender_type == "BEVEL"
    if apply:
        return InputShape(obj.data, with_edges)
    evaluated = obj.evaluated_get(ctx.depsgraph())
    mesh = evaluated.to_mesh()
    try:
        return InputShape(mesh, with_edges)
    finally:
        evaluated.to_mesh_clear()


def bevelled_edges(shape, modifier):
    manifold = [edge for edge in shape.edges if edge[0] is not None]
    if modifier.limit_method == "NONE":
        return manifold
    if modifier.limit_method == "ANGLE":
        return [edge for edge in manifold if edge[0] > modifier.angle_limit + ANGLE_MARGIN]
    return []


def bevelled_vertices(shape, modifier):
    if max(modifier.width, modifier.width_pct) <= 0.0:
        return 0
    touched = {vertex for edge in bevelled_edges(shape, modifier) for vertex in edge[1:]}
    if modifier.affect == "VERTICES":
        return len(touched & shape.corners)
    return len(touched)


def screw_vertices(shape, modifier):
    copies = modifier.steps * modifier.iterations
    if not modifier.use_merge_vertices:
        return shape.vertices * copies
    if modifier.object is not None:
        return shape.vertices
    across = numpy.delete(shape.points, AXES[modifier.axis], axis=1)
    far = int((numpy.linalg.norm(across, axis=1) > modifier.merge_threshold * (1.0 + MERGE_MARGIN) + MERGE_MARGIN).sum())
    return far * copies + shape.vertices - far


def least_vertices(shape, modifier):
    """Lower bound: a screw repeats every vertex steps * iterations times, save those it merges on the axis; a bevel
    replaces every bevelled vertex by at least one profile of segments + 1 vertices and keeps the others."""
    if modifier.type == "SCREW":
        return screw_vertices(shape, modifier)
    return shape.vertices + modifier.segments * bevelled_vertices(shape, modifier)


def check_growth(shape, modifier):
    """Refuse a bevel or screw whose result would certainly pass the vertex limit, before the depsgraph builds it."""
    if shape is None:
        return
    count = least_vertices(shape, modifier)
    if count > MAX_MESH_VERTICES:
        raise bad_args(f"the {modifier.type.lower()} modifier would give at least {count} vertices; the "
                       f"{MAX_MESH_VERTICES.key} limit is {MAX_MESH_VERTICES.plain()} ({MAX_MESH_VERTICES.reason}) "
                       f"{ADVICE[modifier.type]}")
