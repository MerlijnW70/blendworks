"""The shape_key_add command: adds a morph target from offsets."""

from mathutils import Vector

from ..errors import bad_args, not_found
from ..registry import command
from ..limits import ELEMENT_NAME_LENGTH, FRACTION, MAX_RELIEF
from ..schema import number, ref, string, vector3
from ..util import get_mesh_object, rounded

MAX_SHAPE_KEYS = 128


def group_weights(obj, name):
    if name is None:
        return [1.0] * len(obj.data.vertices)
    group = obj.vertex_groups.get(name)
    if group is None:
        raise not_found(f"{obj.name} has no vertex group named {name}; vertex_group makes one")
    weights = [0.0] * len(obj.data.vertices)
    for vertex in obj.data.vertices:
        for element in vertex.groups:
            if element.group == group.index:
                weights[vertex.index] = element.weight
    return weights


@command(
    "shape_key_add",
    "Add a shape key (morph target) from offsets: a world-space displacement and a push along the normals in metres, weighted by a vertex group.",
    {
        "name": ref(string("Mesh object."), "object"),
        "key": string("Shape key name, such as blink or smile.", max_length=ELEMENT_NAME_LENGTH),
        "vertex_group": string("Weights of the offset. Default: every vertex fully."),
        "offset": vector3("Displacement [x, y, z] in world metres.", [0.0, 0.0, 0.0]),
        "normal": number("Push along each vertex normal in metres; negative pulls in.", -MAX_RELIEF, MAX_RELIEF, 0.0),
        "value": number("Starting value of the key.", 0.0, FRACTION, 0.0),
    },
    ["name", "key"],
    family="animation",
    intents=("morph target that closes the eyes", "blend shape for a bulge animated over time"),
    nearest=(("clip_keys", "to animate its value with shape_key and channel value"),),
)
def shape_key_add(ctx, args):
    obj = get_mesh_object(args["name"])
    mesh = obj.data
    if mesh.users > 1:
        raise bad_args(f"{obj.name} shares its mesh with another object; duplicate it unlinked first")
    keys = mesh.shape_keys
    if keys is not None and args["key"] in keys.key_blocks:
        raise bad_args(f"{obj.name} already has a shape key named {args['key']}")
    if keys is not None and len(keys.key_blocks) >= MAX_SHAPE_KEYS:
        raise bad_args(f"{obj.name} already has {MAX_SHAPE_KEYS} shape keys")
    offset = Vector(args["offset"])
    if offset.length == 0 and args["normal"] == 0:
        raise bad_args("give offset or normal, or the shape key would change nothing")
    weights = group_weights(obj, args.get("vertex_group"))
    if not any(weight > 0 for weight in weights):
        raise bad_args(f"vertex group {args.get('vertex_group')} has no weighted vertices")
    if keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    basis = mesh.shape_keys.reference_key
    block = obj.shape_key_add(name=args["key"], from_mix=False)
    block.relative_key = basis
    inverse = obj.matrix_world.to_3x3().inverted_safe()
    normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
    moved = 0
    largest = 0.0
    for index, vertex in enumerate(mesh.vertices):
        weight = weights[index]
        if weight <= 0:
            continue
        world_normal = (normal_matrix @ vertex.normal).normalized()
        displacement = (offset + world_normal * args["normal"]) * weight
        block.data[index].co = basis.data[index].co + inverse @ displacement
        largest = max(largest, displacement.length)
        moved += 1
    block.value = args["value"]
    mesh.update()
    return {
        "name": obj.name,
        "key": block.name,
        "keys": [item.name for item in mesh.shape_keys.key_blocks],
        "moved_vertices": moved,
        "largest_offset": rounded(largest),
        "value": block.value,
    }
