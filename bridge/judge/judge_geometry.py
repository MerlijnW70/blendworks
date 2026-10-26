from array import array
from math import inf, sqrt

import bmesh

from judge_common import JudgeError
from judge_uv import UvGrid

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
NON_SHRINKING_MODIFIERS = {"SUBSURF", "MULTIRES", "TRIANGULATE", "SOLIDIFY", "BEVEL", "WEIGHTED_NORMAL", "EDGE_SPLIT"}
WELD_DISTANCE = 1e-6
MAX_NAMES = 64


def guaranteed_triangles(scene):
    total = 0
    for obj in scene.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        growth = 1
        for modifier in obj.modifiers:
            if not modifier.show_render:
                continue
            if modifier.type not in NON_SHRINKING_MODIFIERS:
                growth = 0
                break
            if modifier.type in {"SUBSURF", "MULTIRES"}:
                growth *= 4 ** modifier.render_levels
        total += len(obj.data.polygons) * growth
    return total


def top_ancestor(obj):
    while obj.parent is not None:
        obj = obj.parent
    return obj


class Measurer:
    def __init__(self, triangle_cap):
        self.triangle_cap = triangle_cap
        self.triangles = 0
        self.objects = 0
        self.low = [inf, inf, inf]
        self.high = [-inf, -inf, -inf]
        self.roots = {}
        self.seen = set()
        self.materials = set()
        self.topology = {"nonManifoldEdges": 0, "boundaryEdges": 0, "wireEdges": 0, "nonManifoldVertices": 0, "looseVertices": 0, "looseParts": 0}
        self.uv_grid = UvGrid()
        self.meshes_without_uv = 0
        self.meshes_with_faces = 0

    def measure(self, depsgraph):
        for instance in depsgraph.object_instances:
            obj = instance.object
            if obj.type not in GEOMETRY_TYPES:
                continue
            matrix = instance.matrix_world.copy()
            owner = instance.parent if instance.is_instance and instance.parent is not None else obj
            root = top_ancestor(owner.original)
            key = obj.original.name if not instance.is_instance else f"{obj.original.name}@{owner.original.name}"
            mesh = obj.to_mesh()
            try:
                if mesh is None or len(mesh.vertices) == 0:
                    continue
                self.add(obj, mesh, matrix, key, root)
            finally:
                obj.to_mesh_clear()

    def add(self, obj, mesh, matrix, key, root):
        mesh.calc_loop_triangles()
        self.triangles += len(mesh.loop_triangles)
        if self.triangles > self.triangle_cap:
            raise JudgeError("too_many_triangles", f"the asset has more than {self.triangle_cap} triangles, the judge's cap")
        self.objects += 1
        self.roots[root.name] = root
        self.extend_bounds(mesh, matrix)
        if key in self.seen:
            return
        self.seen.add(key)
        self.collect_materials(obj, mesh)
        self.collect_topology(mesh)
        if len(mesh.polygons) > 0:
            self.meshes_with_faces += 1
            if not self.uv_grid.add_mesh(mesh):
                self.meshes_without_uv += 1

    def extend_bounds(self, mesh, matrix):
        coordinates = array("f", [0.0]) * (len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", coordinates)
        rows = [tuple(matrix[axis]) for axis in range(3)]
        low = self.low
        high = self.high
        for start in range(0, len(coordinates), 3):
            x = coordinates[start]
            y = coordinates[start + 1]
            z = coordinates[start + 2]
            for axis in range(3):
                row = rows[axis]
                value = row[0] * x + row[1] * y + row[2] * z + row[3]
                if value < low[axis]:
                    low[axis] = value
                if value > high[axis]:
                    high[axis] = value

    def collect_materials(self, obj, mesh):
        if len(mesh.polygons) == 0:
            return
        indices = array("i", [0]) * len(mesh.polygons)
        mesh.polygons.foreach_get("material_index", indices)
        slots = obj.material_slots
        for index in set(indices):
            if 0 <= index < len(slots) and slots[index].material is not None:
                self.materials.add(slots[index].material.name[:120])
            elif 0 <= index < len(mesh.materials) and mesh.materials[index] is not None:
                self.materials.add(mesh.materials[index].name[:120])

    def collect_topology(self, mesh):
        topology = self.topology
        graph = bmesh.new()
        try:
            graph.from_mesh(mesh)
            bmesh.ops.remove_doubles(graph, verts=graph.verts[:], dist=WELD_DISTANCE)
            graph.verts.index_update()
            for edge in graph.edges:
                faces = len(edge.link_faces)
                if faces == 0:
                    topology["wireEdges"] += 1
                elif faces == 1:
                    topology["boundaryEdges"] += 1
                elif faces > 2 or not edge.is_contiguous:
                    topology["nonManifoldEdges"] += 1
            for vertex in graph.verts:
                if not vertex.link_edges:
                    topology["looseVertices"] += 1
                elif not vertex.is_manifold and not vertex.is_boundary and not vertex.is_wire and all(edge.is_manifold and edge.is_contiguous for edge in vertex.link_edges):
                    topology["nonManifoldVertices"] += 1
            topology["looseParts"] += count_parts(graph)
        finally:
            graph.free()

    def result(self):
        if self.objects == 0:
            raise JudgeError("no_geometry", "the asset holds no mesh geometry")
        size = [self.high[axis] - self.low[axis] for axis in range(3)]
        centre = [(self.high[axis] + self.low[axis]) / 2 for axis in range(3)]
        bottom_centre = [centre[0], centre[1], self.low[2]]
        if len(self.roots) == 1:
            root = next(iter(self.roots.values()))
            origin = list(root.matrix_world.translation)
            source = f"object {root.name[:120]}"
        else:
            origin = [0.0, 0.0, 0.0]
            source = "scene origin"
        names = sorted(self.materials)
        uv_present = self.meshes_with_faces > 0 and self.meshes_without_uv == 0
        return {
            "triangles": self.triangles,
            "objects": self.objects,
            "bounds": {"min": rounded(self.low), "max": rounded(self.high)},
            "size": rounded(size),
            "origin": {
                "point": rounded(origin),
                "source": source,
                "bottomCentreDistance": round(distance(origin, bottom_centre), 6),
                "centreDistance": round(distance(origin, centre), 6),
            },
            "manifold": dict(self.topology),
            "materials": {"count": len(names), "names": names[:MAX_NAMES]},
            "uv": {
                "present": uv_present,
                "meshesWithoutUv": self.meshes_without_uv,
                "coverage": round(self.uv_grid.coverage(), 6),
                "overlap": round(self.uv_grid.overlap(), 6),
            },
        }


def count_parts(graph):
    parent = list(range(len(graph.verts)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for edge in graph.edges:
        first = find(edge.verts[0].index)
        second = find(edge.verts[1].index)
        if first != second:
            parent[first] = second
    return len({find(index) for index in range(len(parent))})


def distance(first, second):
    return sqrt(sum((first[axis] - second[axis]) ** 2 for axis in range(3)))


def rounded(values):
    return [round(value, 6) + 0.0 for value in values]
