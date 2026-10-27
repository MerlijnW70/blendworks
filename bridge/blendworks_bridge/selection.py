import math

import bpy
from mathutils import Vector

from .errors import bad_args, not_found
from .schema import array, described, integer, number, obj as object_schema, point3, string, vector3

DIRECTIONS = {
    "up": Vector((0, 0, 1)),
    "down": Vector((0, 0, -1)),
    "front": Vector((0, -1, 0)),
    "back": Vector((0, 1, 0)),
    "right": Vector((1, 0, 0)),
    "left": Vector((-1, 0, 0)),
}

FACE_PROPERTIES = {
    "faces": array(
        {"type": "integer", "minimum": 0},
        "Face indices to work on; combined with facing when both are given. Default: all faces.",
        1,
        200_000,
    ),
    "facing": string(
        "Only faces whose world normal points this way (front is -Y, right is +X, up is +Z).",
        enum=list(DIRECTIONS),
    ),
    "facing_angle": number("Largest angle in degrees between a face normal and facing.", 0.0, 90.0, 30.0),
}


SELECTORS = {
    "box": described(
        object_schema({"min": point3("Lowest corner [x, y, z] in metres."), "max": point3("Highest corner [x, y, z] in metres.")}, ["min", "max"]),
        "Only faces whose world-space centre lies inside this box.",
    ),
    "with_material": string("Only faces whose material slot holds this material."),
    "normal": vector3("Only faces whose world normal is within normal_angle of this direction."),
    "normal_angle": number("Largest angle in degrees between a face normal and normal.", 0.0, 180.0, 30.0),
    "island": integer("Only faces of this connected island; islands are numbered from 0 by their lowest face index.", 0),
    "area_min": number("Only faces with at least this world area in square metres.", 0.0),
    "area_max": number("Only faces with at most this world area in square metres.", 0.0),
}
EXTENDED_FACE_PROPERTIES = {**FACE_PROPERTIES, **SELECTORS}
SELECTOR_NAMES = ("faces", "facing", "box", "with_material", "normal", "island", "area_min", "area_max")


def has_selector(args):
    return any(name in args for name in SELECTOR_NAMES)


def face_islands(bm):
    seen = {}
    number = 0
    for start in bm.faces:
        if start.index in seen:
            continue
        seen[start.index] = number
        stack = [start]
        while stack:
            face = stack.pop()
            for edge in face.edges:
                for neighbour in edge.link_faces:
                    if neighbour.index not in seen:
                        seen[neighbour.index] = number
                        stack.append(neighbour)
        number += 1
    return seen


def world_area(matrix, face):
    points = [matrix @ vert.co for vert in face.verts]
    total = Vector((0.0, 0.0, 0.0))
    for index in range(1, len(points) - 1):
        total += (points[index] - points[0]).cross(points[index + 1] - points[0])
    return total.length / 2.0


def material_slots(obj, name):
    if name not in bpy.data.materials:
        raise not_found(f"no material named {name}")
    return {index for index, material in enumerate(obj.data.materials) if material is not None and material.name == name}


def refine_faces(bm, obj, args, faces):
    matrix = obj.matrix_world
    if "box" in args:
        low, high = Vector(args["box"]["min"]), Vector(args["box"]["max"])
        if any(low[i] > high[i] for i in range(3)):
            raise bad_args("box min must not exceed box max on any axis")
        tolerance = 1e-9
        faces = [
            face
            for face in faces
            if all(low[i] - tolerance <= (matrix @ face.calc_center_median())[i] <= high[i] + tolerance for i in range(3))
        ]
    if "with_material" in args:
        slots = material_slots(obj, args["with_material"])
        faces = [face for face in faces if face.material_index in slots]
    if "normal" in args:
        direction = Vector(args["normal"])
        if direction.length == 0:
            raise bad_args("normal must not be zero")
        direction.normalize()
        threshold = math.cos(math.radians(args["normal_angle"])) - 1e-6
        normal_matrix = matrix.to_3x3().inverted_safe().transposed()
        faces = [face for face in faces if _world_normal(normal_matrix, face).dot(direction) >= threshold]
    if "island" in args:
        islands = face_islands(bm)
        faces = [face for face in faces if islands[face.index] == args["island"]]
    if "area_min" in args or "area_max" in args:
        low, high = args.get("area_min", 0.0), args.get("area_max", math.inf)
        faces = [face for face in faces if low - 1e-12 <= world_area(matrix, face) <= high + 1e-12]
    return faces


def select_faces(bm, obj, args, allow_empty=False):
    bm.faces.ensure_lookup_table()
    faces = list(bm.faces)
    if "faces" in args:
        indices = args["faces"]
        out_of_range = [index for index in indices if index >= len(bm.faces)]
        if out_of_range:
            raise bad_args(f"face index {out_of_range[0]} is out of range; {obj.name} has {len(bm.faces)} faces")
        faces = [bm.faces[index] for index in sorted(set(indices))]
    if "facing" in args:
        direction = DIRECTIONS[args["facing"]]
        threshold = math.cos(math.radians(args.get("facing_angle", 30.0))) - 1e-6
        normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
        faces = [face for face in faces if _world_normal(normal_matrix, face).dot(direction) >= threshold]
    faces = refine_faces(bm, obj, args, faces)
    if not faces and not allow_empty:
        raise bad_args(f"no faces of {obj.name} match the selection")
    return faces


def _world_normal(normal_matrix, face):
    normal = normal_matrix @ face.normal
    if normal.length == 0:
        return normal
    return normal.normalized()
