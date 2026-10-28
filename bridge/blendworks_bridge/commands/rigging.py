import bpy
from mathutils import Vector

from ..bones import (
    BONE_FIELDS,
    BONE_SCHEMA,
    MAX_BONES,
    add_bones,
    deforming_armatures,
    apply_bone,
    bones_report,
    check_bone_name,
    check_length,
    get_armature,
    link_parents,
    mirrored_name,
    new_armature,
    rename_roles,
    rig_metadata,
    side_of,
    store_metadata,
    to_world,
)
from ..errors import bad_args, failed, not_found
from ..operators import edit_mode, operator_context
from ..registry import command
from ..rig_layouts import TEMPLATES, Frame, check_landmarks, ground_height, humanoid, prop, quadruped
from ..schema import array, boolean, described, names, number, obj as object_schema, point3, string, vector3
from ..util import get_mesh_object, merge_bounds, object_bounds, require_free_name, vec

EDIT_FIELDS = {
    "name": BONE_FIELDS["name"],
    "rename": string("New name for the bone; vertex groups and constraints follow it.", max_length=63),
    "head": BONE_FIELDS["head"],
    "tail": BONE_FIELDS["tail"],
    "roll": number("Roll about the bone's own axis in degrees.", -360.0, 360.0),
    "parent": BONE_FIELDS["parent"],
    "clear_parent": boolean("Make the bone a root bone."),
    "connect": boolean("Join the head to the parent's tail."),
    "deform": boolean("The bone deforms skinned meshes."),
}
EDIT_SCHEMA = object_schema(EDIT_FIELDS, ["name"])
LANDMARK = object_schema({"name": string("Landmark name, such as left_knee or hinge.", max_length=64), "point": point3()}, ["name", "point"])
DEFAULT_AXES = {"hinge": [1.0, 0.0, 0.0], "piston": [0.0, 0.0, 1.0], "wheel": [1.0, 0.0, 0.0]}


def bone_list(description, minimum=1):
    return array(BONE_SCHEMA, description, minimum, MAX_BONES)


@command(
    "armature_create",
    "Create an armature object, optionally with bones: head, tail and roll in metres and degrees, parent, connect and deform flags.",
    {
        "name": string("Armature object name; must be unused."),
        "location": vector3("Armature origin in metres. Bone points are world space either way.", [0.0, 0.0, 0.0]),
        "bones": bone_list("Bones to add, parents before or after their children.", 0),
    },
    ["name"],
    family="rigging",
    intents=("make a skeleton for a character", "new armature with bones", "a chain of bones for a machine from scratch"),
    nearest=(("rig_template", "for a ready humanoid, quadruped or prop rig fitted to a mesh"),),
)
def armature_create(ctx, args):
    require_free_name(args["name"])
    armature = new_armature(ctx, args["name"], args["location"])
    if args.get("bones"):
        add_bones(ctx, armature, args["bones"])
    return {"name": armature.name, "bones": bones_report(armature)}


@command(
    "bone_add",
    "Add bones to an armature: head, tail, roll, parent, connect and deform per bone, in world-space metres.",
    {"armature": string("Armature object."), "bones": bone_list("Bones to add.")},
    ["armature", "bones"],
    family="rigging",
    intents=("add a tail bone to the rig", "extra bones on an armature"),
    nearest=(("bone_edit", "to move, rename or reparent existing bones"),),
)
def bone_add(ctx, args):
    armature = get_armature(args["armature"])
    added = add_bones(ctx, armature, args["bones"])
    return {"armature": armature.name, "added": added, "bones": bones_report(armature, added), "count": len(armature.data.bones)}


@command(
    "bone_edit",
    "Edit bones: rename, move head or tail, set roll in degrees, reparent or clear the parent, connect, and the deform flag.",
    {"armature": string("Armature object."), "bones": array(EDIT_SCHEMA, "Bones to change, each by its current name.", 1, MAX_BONES)},
    ["armature", "bones"],
    family="rigging",
    intents=("rename a bone and change its parent", "orient a bone with roll", "turn off deform on a control bone"),
    nearest=(("bone_add", "to add new bones"), ("bone_mirror", "to copy one side to the other")),
)
def bone_edit(ctx, args):
    armature = get_armature(args["armature"])
    specs = args["bones"]
    seen = set()
    renames = {}
    for spec in specs:
        if spec["name"] in seen:
            raise bad_args(f"bone {spec['name']} is listed twice")
        seen.add(spec["name"])
        if spec["name"] not in armature.data.bones:
            raise not_found(f"{armature.name} has no bone named {spec['name']}")
        if "parent" in spec and spec.get("clear_parent"):
            raise bad_args(f"bone {spec['name']}: give parent or clear_parent, not both")
        if "rename" in spec:
            check_bone_name(spec["rename"])
            if spec["rename"] in armature.data.bones and spec["rename"] != spec["name"]:
                raise bad_args(f"{armature.name} already has a bone named {spec['rename']}")
            renames[spec["name"]] = spec["rename"]
    with edit_mode(ctx.view_layer, armature):
        bones = armature.data.edit_bones
        for spec in specs:
            edit_bone = bones[spec["name"]]
            apply_bone(armature, edit_bone, spec)
            check_length(spec["name"], edit_bone.head, edit_bone.tail)
        for spec in specs:
            if "rename" in spec:
                bones[spec["name"]].name = spec["rename"]
        relinks = [dict(spec, name=spec.get("rename", spec["name"])) for spec in specs]
        for spec in relinks:
            spec.pop("rename", None)
        link_parents(armature, relinks)
    rename_roles(armature, renames)
    changed = [spec.get("rename", spec["name"]) for spec in specs]
    return {"armature": armature.name, "bones": bones_report(armature, changed), "renamed": renames}


@command(
    "bone_mirror",
    "Mirror bones across the armature's X = 0 plane by name (Left/Right, .L/.R, _L/_R): makes or updates the other side.",
    {
        "armature": string("Armature object."),
        "bones": names("Bones to mirror. Default: every bone on the from side."),
        "from_side": string("The side to copy; left is +X.", ["left", "right"], "left"),
    },
    ["armature"],
    family="rigging",
    intents=("copy the left arm bones to the right", "symmetric legs from one side"),
    nearest=(("bone_edit", "to adjust a single bone"),),
)
def bone_mirror(ctx, args):
    armature = get_armature(args["armature"])
    side = args["from_side"]
    if "bones" in args:
        chosen = []
        for name in args["bones"]:
            if name not in armature.data.bones:
                raise not_found(f"{armature.name} has no bone named {name}")
            if side_of(name)[0] != side:
                raise bad_args(f"bone {name} is not named as a {side} bone (Left/Right, .L/.R, _L/_R)")
            chosen.append(name)
    else:
        chosen = [bone.name for bone in armature.data.bones if side_of(bone.name)[0] == side]
    if not chosen:
        raise bad_args(f"{armature.name} has no {side} bones to mirror")
    created = [mirrored_name(name) for name in chosen if mirrored_name(name) not in armature.data.bones]
    if len(armature.data.bones) + len(created) > MAX_BONES:
        raise bad_args(f"an armature holds at most {MAX_BONES} bones")
    with edit_mode(ctx.view_layer, armature):
        for edit_bone in armature.data.edit_bones:
            picked = edit_bone.name in chosen
            edit_bone.select = picked
            edit_bone.select_head = picked
            edit_bone.select_tail = picked
        with bpy.context.temp_override(**operator_context(armature)):
            done = bpy.ops.armature.symmetrize(direction="POSITIVE_X" if side == "left" else "NEGATIVE_X")
        if "FINISHED" not in done:
            raise failed("Blender's symmetrize did not run")
    pairs = []
    for name in chosen:
        other = mirrored_name(name)
        bone = armature.data.bones.get(other)
        if bone is None:
            raise failed(f"symmetrize made no bone {other}")
        pairs.append({"from": name, "to": other, "head": vec(to_world(armature, bone.head_local)), "tail": vec(to_world(armature, bone.tail_local)), "parent": bone.parent.name if bone.parent else None})
    return {"armature": armature.name, "pairs": pairs, "created": sorted(created), "count": len(armature.data.bones)}


def fit_frame(ctx, args):
    if "fit" in args and "bounds" in args:
        raise bad_args("give fit or bounds, not both")
    if "bounds" in args:
        return Frame(args["bounds"]["min"], args["bounds"]["max"]), []
    if "fit" not in args:
        raise bad_args("give fit (meshes to fit the rig to) or bounds")
    meshes = [get_mesh_object(name) for name in args["fit"]]
    depsgraph = ctx.depsgraph()
    bounds = merge_bounds([object_bounds(mesh, depsgraph) for mesh in meshes])
    if bounds is None:
        raise bad_args("the fit meshes have no vertices")
    return Frame(*bounds), meshes


def limb_spread(meshes, frame, fraction):
    offsets = []
    for mesh in meshes:
        matrix = mesh.matrix_world
        for vertex in mesh.data.vertices:
            point = matrix @ vertex.co
            if point.z <= frame.low.z + fraction * frame.size.z and point.x > frame.centre.x:
                offsets.append(point.x - frame.centre.x)
    if len(offsets) < 3:
        return None
    offsets.sort()
    return offsets[len(offsets) // 2]


@command(
    "rig_template",
    "Build a humanoid, quadruped or prop rig (hinge, piston, wheel) fitted to a mesh's bounds or to named landmarks; returns the bone map.",
    {
        "template": string("Rig kind.", list(TEMPLATES)),
        "name": string("Armature object name; must be unused."),
        "fit": names("Meshes whose world bounds the rig is fitted to."),
        "bounds": described(object_schema({"min": point3("Lowest corner."), "max": point3("Highest corner.")}, ["min", "max"]), "World box to fit the rig to, instead of fit."),
        "landmarks": array(LANDMARK, "Named points that override the fitted ones, such as left_knee, hips or hinge; right_ points default to the mirror of left_ ones.", 1, 64),
        "pose": string("Humanoid arm pose of the mesh: a (arms down at 25 to 70 degrees, fitted to the width) or t (arms level).", ["a", "t"], "a"),
        "axis": vector3("Prop axis: the hinge or wheel axle, or the piston stroke. Default x for hinge and wheel, z for piston."),
    },
    ["template", "name"],
    family="rigging",
    intents=("rig a humanoid character", "skeleton for a four-legged animal", "bones for a chest lid, a piston or a wheel"),
    nearest=(("armature_create", "for a custom skeleton bone by bone"), ("skin_bind", "to bind the mesh once the rig fits")),
)
def rig_template(ctx, args):
    require_free_name(args["name"])
    template = args["template"]
    frame, meshes = fit_frame(ctx, args)
    landmarks = {}
    for entry in args.get("landmarks", []):
        if entry["name"] in landmarks:
            raise bad_args(f"landmark {entry['name']} is given twice")
        landmarks[entry["name"]] = entry["point"]
    check_landmarks(template, landmarks)
    if "axis" in args and template in ("humanoid", "quadruped"):
        raise bad_args("axis applies to the hinge, piston and wheel templates")
    axis = Vector(args.get("axis", DEFAULT_AXES.get(template, [1.0, 0.0, 0.0])))
    if axis.length < 1e-6:
        raise bad_args("axis must not be zero")
    axis.normalize()
    if template == "humanoid":
        bones, roles = humanoid(frame, landmarks, args["pose"], limb_spread(meshes, frame, 0.25) if meshes else None)
    elif template == "quadruped":
        bones, roles = quadruped(frame, landmarks, limb_spread(meshes, frame, 0.2) if meshes else None)
    else:
        bones, roles = prop(template, frame, landmarks, axis)
    armature = new_armature(ctx, args["name"], [0.0, 0.0, 0.0])
    add_bones(ctx, armature, bones)
    metadata = {"template": template, "roles": roles, "ground": ground_height(bones, template, frame), "height": frame.size.z}
    if template not in ("humanoid", "quadruped"):
        metadata["axis"] = list(axis)
    store_metadata(armature, metadata)
    return {
        "name": armature.name,
        "template": template,
        "bone_map": roles,
        "bounds": {"min": vec(frame.low), "max": vec(frame.high)},
        "bones": bones_report(armature),
        "count": len(armature.data.bones),
    }


@command(
    "rig_info",
    "Read an armature: its bones with head, tail, roll, parent and deform flag, the template bone map, constraints and skinned meshes.",
    {"armature": string("Armature object.")},
    ["armature"],
    mutates=False,
    family="rigging",
    intents=("list the bones of the skeleton", "which bones deform and what is the bone map"),
    nearest=(("clip_info", "for the animation clips"),),
)
def rig_info(ctx, args):
    armature = get_armature(args["armature"])
    metadata = rig_metadata(armature)
    constraints = []
    for pose_bone in armature.pose.bones:
        for constraint in pose_bone.constraints:
            entry = {"bone": pose_bone.name, "name": constraint.name, "type": constraint.type.lower(), "enabled": constraint.enabled}
            if getattr(constraint, "subtarget", ""):
                entry["subtarget"] = constraint.subtarget
            constraints.append(entry)
    skinned = sorted(obj.name for obj in ctx.scene.objects if obj.type == "MESH" and armature in deforming_armatures(obj))
    return {
        "name": armature.name,
        "template": metadata.get("template"),
        "bone_map": metadata.get("roles", {}),
        "bones": bones_report(armature),
        "deform_bones": sum(1 for bone in armature.data.bones if bone.use_deform),
        "constraints": constraints,
        "skinned_meshes": skinned,
    }

