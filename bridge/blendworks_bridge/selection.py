import math

from mathutils import Vector

from .errors import bad_args
from .schema import array, number, string

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


def select_faces(bm, obj, args):
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
    if not faces:
        raise bad_args(f"no faces of {obj.name} match the selection")
    return faces


def _world_normal(normal_matrix, face):
    normal = normal_matrix @ face.normal
    if normal.length == 0:
        return normal
    return normal.normalized()
