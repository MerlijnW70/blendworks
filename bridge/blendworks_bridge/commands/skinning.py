import bpy

from ..bones import deforming_armatures, get_armature
from ..errors import bad_args, failed
from ..operators import only_selected, operator_context
from ..registry import command
from ..limits import BONE_INFLUENCES, ELEMENT_NAME_LENGTH, FRACTION, RIGID_PARTS, SMOOTHING_PASSES
from ..schema import array, boolean, integer, names, number, obj as object_schema, point3, ref, string
from ..selection import EXTENDED_FACE_PROPERTIES, has_selector, select_faces
from ..util import EditMesh, get_mesh_object
from ..weights import (
    influence_counts,
    islands,
    limited,
    nearest_bone,
    neighbours,
    normalized,
    read_weights,
    region_vertices,
    segments,
    smoothed,
    whole_parts,
    write_weights,
)

METHODS = {"automatic": "ARMATURE_AUTO", "envelope": "ARMATURE_ENVELOPE", "none": "ARMATURE_NAME"}
RIGID = object_schema(
    {
        "bone": string("Deforming bone that carries the whole part.", max_length=ELEMENT_NAME_LENGTH),
        "vertex_group": string("The part: the vertices of this vertex group."),
        "island": integer("The part: this loose part, numbered from 0 by lowest vertex index.", 0),
        "near": point3("The part: the loose part whose surface passes nearest to this world point."),
    },
    ["bone"],
)


@command(
    "vertex_group",
    "Create or change a vertex group from a face selection (box, island, material, normal): replace, add or remove vertices with a weight.",
    {
        "name": ref(string("Mesh object."), "object"),
        "group": string("Vertex group name.", max_length=ELEMENT_NAME_LENGTH),
        "weight": number("Weight of the chosen vertices.", 0.0, FRACTION, 1.0),
        "mode": string("replace makes the group exactly the chosen vertices; add and remove change it.", ["replace", "add", "remove"], "replace"),
        **EXTENDED_FACE_PROPERTIES,
    },
    ["name", "group"],
    family="rigging",
    intents=("vertex group of the head vertices", "mark the lid faces as a group"),
    nearest=(("skin_bind", "to bind to an armature with rigid parts"),),
)
def vertex_group(ctx, args):
    obj = get_mesh_object(args["name"])
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args) if has_selector(args) else list(bm.faces)
        chosen = sorted({vert.index for face in faces for vert in face.verts})
    if not chosen:
        raise bad_args(f"no vertices of {obj.name} match the selection")
    group = obj.vertex_groups.get(args["group"])
    if group is None:
        if args["mode"] == "remove":
            raise bad_args(f"{obj.name} has no vertex group named {args['group']}")
        group = obj.vertex_groups.new(name=args["group"])
    if args["mode"] == "replace":
        group.remove(list(range(len(obj.data.vertices))))
    if args["mode"] == "remove":
        group.remove(chosen)
    else:
        group.add(chosen, args["weight"], "REPLACE")
    members = sum(1 for vertex in obj.data.vertices if any(element.group == group.index for element in vertex.groups))
    return {"name": obj.name, "group": group.name, "vertices": members, "changed": len(chosen)}


def unbind(obj, armature, bone_names):
    for modifier in list(obj.modifiers):
        if modifier.type == "ARMATURE" and modifier.object == armature:
            obj.modifiers.remove(modifier)
    for group in list(obj.vertex_groups):
        if group.name in bone_names:
            obj.vertex_groups.remove(group)


def bind_with_blender(ctx, meshes, armature, method, deform):
    pose_position = armature.data.pose_position
    armature.data.pose_position = "REST"
    switched = [bone for bone in armature.data.bones if bone.use_deform and bone.name not in deform]
    for bone in switched:
        bone.use_deform = False
    try:
        ctx.view_layer.update()
        with only_selected(ctx.view_layer, armature, meshes + [armature]):
            with bpy.context.temp_override(**operator_context(armature, meshes + [armature])):
                done = bpy.ops.object.parent_set(type=METHODS[method], keep_transform=True)
        if "FINISHED" not in done:
            raise failed("Blender did not bind the meshes")
    finally:
        for bone in switched:
            bone.use_deform = True
        armature.data.pose_position = pose_position
        ctx.view_layer.update()
    for obj in meshes:
        if obj.parent == armature:
            world = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = world
    ctx.view_layer.update()


def refine(obj, armature, deform, args):
    mesh = obj.data
    weights = read_weights(obj, deform)
    labels, count = islands(mesh)
    if args["smooth"] > 0:
        weights = smoothed(weights, neighbours(mesh), args["smooth"], args["smooth_factor"], set())
    rigid_vertices = 0
    if args["rigid_parts"]:
        weights = whole_parts(weights, labels, count)
    for entry in args.get("rigid", []):
        if entry["bone"] not in deform:
            raise bad_args(f"rigid part bone {entry['bone']} is not one of the deforming bones this bind uses")
        region = region_vertices(obj, entry, labels)
        for index in region:
            weights[index] = {entry["bone"]: 1.0}
        rigid_vertices += len(region)
    unweighted_before = sum(1 for entry in weights if not entry)
    filled = 0
    if args["fill_unweighted"] and unweighted_before:
        bone_segments = segments(armature, sorted(deform))
        matrix = obj.matrix_world
        for index, entry in enumerate(weights):
            if not entry:
                weights[index] = {nearest_bone(matrix @ mesh.vertices[index].co, bone_segments): 1.0}
                filled += 1
    weights = limited(weights, args["max_influences"])
    if args["normalize"]:
        weights = normalized(weights)
    write_weights(obj, sorted(deform), weights)
    most, unweighted = influence_counts(weights)
    return {
        "name": obj.name,
        "vertices": len(mesh.vertices),
        "parts": count,
        "max_influences": most,
        "unweighted_after_bind": unweighted_before,
        "filled": filled,
        "unweighted": unweighted,
        "rigid_vertices": rigid_vertices,
        "groups": sorted({name for entry in weights for name in entry}),
    }


@command(
    "skin_bind",
    "Bind meshes to an armature with automatic (heat) weights: limit influences (default 4), normalise, smooth, rigid parts; reports unweighted vertices.",
    {
        "meshes": ref(names("Meshes to bind."), "object"),
        "armature": ref(string("Armature to bind to."), "object"),
        "weights": string("automatic heat weights, bone envelopes, or none (only rigid parts and the nearest-bone fill).", list(METHODS), "automatic"),
        "bones": names("Deforming bones the weights may use, such as the leg bones for a leg mesh. Default: every deforming bone."),
        "max_influences": integer("Most bones per vertex; extra weights are dropped, smallest first.", 1, BONE_INFLUENCES, 4),
        "normalize": boolean("Make every vertex's weights sum to 1.", True),
        "smooth": integer("Smoothing passes over the mesh edges before limiting.", 0, SMOOTHING_PASSES, 0),
        "smooth_factor": number("How far each pass moves a weight towards its neighbours' mean.", 0.0, FRACTION, 0.5),
        "rigid": array(RIGID, "Parts that move with one bone only: a vertex group, a loose part by number or near a point.", 1, RIGID_PARTS),
        "rigid_parts": boolean("Give every loose part wholly to the bone with the most weight on it, for rigid props and mannequins.", False),
        "fill_unweighted": boolean("Give each vertex left without weight to its nearest deforming bone.", True),
    },
    ["meshes", "armature"],
    slow=True,
    family="rigging",
    intents=("skin the body to the skeleton", "automatic weights with four bones per vertex", "bind the chest so the lid moves with its bone"),
    nearest=(("vertex_group", "to mark a part for rigid binding first"), ("rig_template", "to make the rig")),
)
def skin_bind(ctx, args):
    armature = get_armature(args["armature"])
    meshes = [get_mesh_object(name) for name in args["meshes"]]
    every = {bone.name for bone in armature.data.bones if bone.use_deform}
    if not every:
        raise bad_args(f"{armature.name} has no deforming bones")
    deform = set(args.get("bones", every))
    stray = sorted(deform - every)
    if stray:
        raise bad_args(f"{', '.join(stray)} is not a deforming bone of {armature.name}")
    for obj in meshes:
        others = [rig.name for rig in deforming_armatures(obj) if rig != armature]
        if others:
            raise bad_args(f"{obj.name} is already skinned to {others[0]}")
        if obj.data.users > 1:
            raise bad_args(f"{obj.name} shares its mesh with another object; duplicate it unlinked first")
        unbind(obj, armature, every)
    bind_with_blender(ctx, meshes, armature, args["weights"], deform)
    results = [refine(obj, armature, deform, args) for obj in meshes]
    return {
        "armature": armature.name,
        "weights": args["weights"],
        "meshes": results,
        "unweighted": sum(entry["unweighted"] for entry in results),
        "max_influences": max(entry["max_influences"] for entry in results),
        "normalized": args["normalize"],
        "rest_pose": True,
    }
