from mathutils import Matrix, Vector

from ..errors import bad_args
from ..registry import command
from ..schema import boolean, string, vector3
from ..util import bounds_of, compensate_children, degrees, euler_from_degrees, evaluated_points, get_mesh_object
from ..util import get_object, vec

TRANSFORMABLE_DATA = ("MESH", "CURVE")


@command(
    "transform",
    "Set (or with relative, add to) an object's location in metres, rotation in degrees and scale.",
    {
        "name": string("Object to transform."),
        "location": vector3("Location in metres."),
        "rotation": vector3("Euler XYZ rotation in degrees."),
        "scale": vector3("Scale factors; none may be zero.", minimum=-1000.0, maximum=1000.0),
        "relative": boolean("Add location and rotation, and multiply scale, instead of setting them.", False),
    },
    ["name"],
)
def transform(ctx, args):
    obj = get_object(args["name"])
    if not any(key in args for key in ("location", "rotation", "scale")):
        raise bad_args("give at least one of location, rotation, scale")
    if "scale" in args and any(factor == 0 for factor in args["scale"]):
        raise bad_args("scale factors must not be zero")
    relative = args["relative"]
    if "location" in args:
        offset = Vector(args["location"])
        obj.location = obj.location + offset if relative else offset
    if "rotation" in args:
        obj.rotation_mode = "XYZ"
        current = degrees(obj.rotation_euler) if relative else [0.0, 0.0, 0.0]
        obj.rotation_euler = euler_from_degrees([a + b for a, b in zip(current, args["rotation"])])
    if "scale" in args:
        factors = Vector(args["scale"])
        obj.scale = Vector([a * b for a, b in zip(obj.scale, factors)]) if relative else factors
    return {
        "name": obj.name,
        "location": vec(obj.location),
        "rotation": degrees(obj.rotation_euler),
        "scale": vec(obj.scale),
    }


@command(
    "apply_transform",
    "Bake an object's location, rotation and/or scale into its mesh so they become zero, zero and one.",
    {
        "name": string("Mesh or curve object."),
        "location": boolean("Apply the location.", False),
        "rotation": boolean("Apply the rotation.", True),
        "scale": boolean("Apply the scale.", True),
    },
    ["name"],
)
def apply_transform(ctx, args):
    obj = editable_data_object(args["name"])
    location, rotation, scale = obj.matrix_basis.decompose()
    keep_location = Matrix.Identity(4) if args["location"] else Matrix.Translation(location)
    keep_rotation = Matrix.Identity(4) if args["rotation"] else rotation.to_matrix().to_4x4()
    keep_scale = Matrix.Identity(4) if args["scale"] else Matrix.Diagonal(scale.to_4d())
    new_basis = keep_location @ keep_rotation @ keep_scale
    data_matrix = new_basis.inverted() @ obj.matrix_basis
    bake(ctx, obj, data_matrix)
    obj.matrix_basis = new_basis
    compensate_children(obj, data_matrix)
    ctx.view_layer.update()
    return {
        "name": obj.name,
        "location": vec(obj.location),
        "rotation": degrees(obj.rotation_euler),
        "scale": vec(obj.scale),
        "dimensions": vec(obj.dimensions),
    }


@command(
    "set_origin",
    "Move an object's origin without moving its geometry: to its bounds centre, its bottom centre, or the cursor.",
    {
        "name": string("Mesh object."),
        "to": string(
            "geometry_centre: centre of the bounds (modifiers included); bottom_centre: centre of the bounds in X and Y at the lowest Z "
            "in world space; cursor: the 3D cursor or point.",
            ["geometry_centre", "bottom_centre", "cursor"],
        ),
        "point": vector3("World point in metres used with to=cursor instead of the scene's 3D cursor."),
    },
    ["name", "to"],
)
def set_origin(ctx, args):
    obj = editable_data_object(args["name"], mesh_only=True)
    if "point" in args and args["to"] != "cursor":
        raise bad_args("point applies only to to=cursor")
    world = obj.matrix_world.copy()
    points = evaluated_points(obj, ctx.depsgraph())
    if not points and args["to"] != "cursor":
        raise bad_args(f"{obj.name} has no vertices")
    if args["to"] == "geometry_centre":
        low, high = bounds_of([world.inverted() @ point for point in points])
        local_point = (low + high) / 2
    elif args["to"] == "bottom_centre":
        low, high = bounds_of(points)
        world_point = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
        local_point = world.inverted() @ world_point
    else:
        world_point = Vector(args["point"]) if "point" in args else ctx.scene.cursor.location.copy()
        local_point = world.inverted() @ world_point
    shift = Matrix.Translation(-local_point)
    bake(ctx, obj, shift)
    obj.matrix_basis = obj.matrix_basis @ Matrix.Translation(local_point)
    compensate_children(obj, shift)
    ctx.view_layer.update()
    return {"name": obj.name, "origin": vec(obj.matrix_world.translation), "location": vec(obj.location)}


def editable_data_object(name, mesh_only=False):
    obj = get_mesh_object(name) if mesh_only else get_object(name)
    if obj.type not in TRANSFORMABLE_DATA:
        raise bad_args(f"{name} is a {obj.type.lower()}; only meshes and curves can be changed this way")
    if obj.data.users > 1:
        raise bad_args(f"{name} shares its data with other objects; duplicate it without linking first")
    return obj


def bake(ctx, obj, matrix):
    if obj.type == "MESH":
        ctx.txn.touch_mesh(obj.data)
    obj.data.transform(matrix)
    obj.data.update()
