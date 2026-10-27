from array import array
from math import inf

from judge_common import JudgeError, distance, rounded
from judge_objects import ObjectTable
from judge_parts import PartCollector
from judge_shells import empty_topology, mesh_topology
from judge_surface import Surface, triangle_area
from judge_uv import UvGrid

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
WELD_DISTANCE = 1e-6
DEGENERATE_AREA = WELD_DISTANCE * WELD_DISTANCE
MAX_NAMES = 64


def top_ancestor(obj):
    while obj.parent is not None:
        obj = obj.parent
    return obj


def world_coordinates(mesh, matrix):
    coordinates = array("f", [0.0]) * (len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coordinates)
    rows = [tuple(matrix[axis]) for axis in range(3)]
    (a, b, c, d), (e, f, g, h), (i, j, k, l) = rows
    world = []
    for start in range(0, len(coordinates), 3):
        x = coordinates[start]
        y = coordinates[start + 1]
        z = coordinates[start + 2]
        world.append((a * x + b * y + c * z + d, e * x + f * y + g * z + h, i * x + j * y + k * z + l))
    return world


def face_vertices(mesh):
    loops = array("i", [0]) * len(mesh.loops)
    mesh.loops.foreach_get("vertex_index", loops)
    return set(loops)


def triangle_areas(mesh, world):
    corners = array("i", [0]) * (len(mesh.loop_triangles) * 3)
    mesh.loop_triangles.foreach_get("vertices", corners)
    return [triangle_area(world[corners[start]], world[corners[start + 1]], world[corners[start + 2]]) for start in range(0, len(corners), 3)]


def extend(low, high, points):
    for point in points:
        for axis in range(3):
            value = point[axis]
            if value < low[axis]:
                low[axis] = value
            if value > high[axis]:
                high[axis] = value


class Measurer:
    def __init__(self, triangle_cap, floating_tolerance=None, integrity=True, objects=False):
        self.triangle_cap = triangle_cap
        self.parts = None if floating_tolerance is None else PartCollector(floating_tolerance, WELD_DISTANCE)
        self.surface = Surface(DEGENERATE_AREA, WELD_DISTANCE) if integrity else None
        self.table = ObjectTable() if objects else None
        self.triangles = 0
        self.objects = 0
        self.low = [inf, inf, inf]
        self.high = [-inf, -inf, -inf]
        self.roots = {}
        self.datablocks = {}
        self.shells = {"count": 0, "closed": 0, "inverted": 0}
        self.materials = set()
        self.material_blocks = {}
        self.faces_without_material = False
        self.topology = empty_topology()
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
            label = obj.original.name if not instance.is_instance else f"{obj.original.name}@{owner.original.name}"
            data_key = obj.data.as_pointer() if obj.data is not None else label
            mesh = obj.to_mesh()
            try:
                if mesh is None or len(mesh.vertices) == 0:
                    continue
                self.add(obj, mesh, matrix, label, data_key, root)
            finally:
                obj.to_mesh_clear()

    def add(self, obj, mesh, matrix, label, data_key, root):
        mesh.calc_loop_triangles()
        triangles = len(mesh.loop_triangles)
        self.triangles += triangles
        if self.triangles > self.triangle_cap:
            raise JudgeError("too_many_triangles", f"the asset has more than {self.triangle_cap} triangles, the judge's cap")
        self.objects += 1
        self.roots[root.name] = root
        world = world_coordinates(mesh, matrix)
        on_faces = [world[index] for index in face_vertices(mesh)]
        extend(self.low, self.high, on_faces)
        areas = triangle_areas(mesh, world)
        materials = self.collect_materials(obj, mesh)
        if self.parts is not None:
            self.parts.add(label, mesh, matrix)
        if self.surface is not None:
            self.surface.add(mesh, world, areas)
        if self.table is not None:
            low, high = [inf, inf, inf], [-inf, -inf, -inf]
            extend(low, high, on_faces)
            self.table.add(label, triangles, low, high, tuple(matrix.translation), materials)
        shells = self.datablocks.get(data_key)
        if shells is None:
            topology, shells = mesh_topology(mesh, WELD_DISTANCE)
            self.datablocks[data_key] = shells
            for key, value in topology.items():
                self.topology[key] += value
            if len(mesh.polygons) > 0:
                self.meshes_with_faces += 1
                if not self.uv_grid.add_mesh(mesh, areas, DEGENERATE_AREA):
                    self.meshes_without_uv += 1
        for key, value in shells.items():
            self.shells[key] += value

    def collect_materials(self, obj, mesh):
        if len(mesh.polygons) == 0:
            return set()
        indices = array("i", [0]) * len(mesh.polygons)
        mesh.polygons.foreach_get("material_index", indices)
        slots = obj.material_slots
        used = set()
        for index in set(indices):
            if 0 <= index < len(slots) and slots[index].material is not None:
                material = slots[index].material
            elif 0 <= index < len(mesh.materials) and mesh.materials[index] is not None:
                material = mesh.materials[index]
            else:
                self.faces_without_material = True
                continue
            used.add(material.name)
            self.materials.add(material.name[:120])
            self.material_blocks[material.name] = material
        return used

    def uv_layout(self):
        return self.uv_grid.finish()

    def result(self):
        if self.objects == 0:
            raise JudgeError("no_geometry", "the asset holds no mesh geometry")
        if self.low[0] == inf:
            raise JudgeError("no_geometry", "the asset holds no faces, only loose vertices or edges")
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
        grid = self.uv_layout()
        measured = {
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
                "coverage": round(grid.coverage(), 6),
                "overlap": round(grid.overlap(), 6),
                "outsideUnitSquare": round(grid.outside(), 6),
            },
            "shells": dict(self.shells),
        }
        if self.surface is not None:
            visibility = self.surface.visibility()
            measured["faces"] = {
                "degenerate": self.surface.degenerate,
                "duplicate": self.surface.duplicate,
                "hiddenRatio": round(visibility["hiddenRatio"], 6),
                "hiddenFaces": visibility["hiddenFaces"],
                "tested": visibility["tested"],
                "sampled": visibility["sampled"],
            }
            measured["visibleTriangles"] = visibility["visibleTriangles"]
        if self.parts is not None:
            measured["floating"] = self.parts.result()
        if self.table is not None:
            measured["objectList"] = self.table.result()
        return measured

