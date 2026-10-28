import math

from mathutils import Vector

from ..bones import add_bones, get_armature, require_bone, rig_metadata, to_world
from ..errors import bad_args
from ..posing import bend_direction
from ..registry import command
from ..schema import array, boolean, integer, length, number, string, vector3
from ..util import get_object, rounded, vec

KINDS = {"copy_rotation": "COPY_ROTATION", "damped_track": "DAMPED_TRACK", "limit_rotation": "LIMIT_ROTATION", "copy_location": "COPY_LOCATION"}
SPACES = {"world": "WORLD", "pose": "POSE", "local": "LOCAL"}
TRACK_AXES = {"y": "TRACK_Y", "-y": "TRACK_NEGATIVE_Y", "x": "TRACK_X", "-x": "TRACK_NEGATIVE_X", "z": "TRACK_Z", "-z": "TRACK_NEGATIVE_Z"}
MIXES = {"replace": "REPLACE", "add": "ADD", "before": "BEFORE", "after": "AFTER"}
MAX_CONSTRAINTS = 32
POLE_TOLERANCE = 1e-5


def chain_of(armature, bone, length_count):
    chain = [require_bone(armature, bone)]
    while len(chain) < length_count:
        parent = chain[-1].parent
        if parent is None:
            raise bad_args(f"{bone} has only {len(chain)} bone(s) above it; lower chain_length")
        chain.append(parent)
    return chain


def control_parent(armature, given, chain):
    if given:
        require_bone(armature, given)
        return given
    root = rig_metadata(armature).get("roles", {}).get("root")
    if root and root in armature.data.bones:
        return root
    top = chain[-1]
    while top.parent is not None:
        top = top.parent
    return None if top in chain else top.name


def signed_angle(first, second, normal):
    angle = first.angle(second) if first.length and second.length else 0.0
    return -angle if first.cross(second).dot(normal) > 0 else angle


def pole_angle(base, tip, pole):
    base_head = base.head_local
    base_tail = base.tail_local
    pole_normal = (tip.tail_local - base_head).cross(Vector(pole) - base_head)
    projected = pole_normal.cross(base_tail - base_head)
    x_axis = base.matrix_local.to_3x3().col[0]
    return signed_angle(x_axis, projected, base_tail - base_head)


@command(
    "ik_chain",
    "Add an IK chain to a bone: a target bone (made at the tip unless named) or object, chain length, and a pole target that keeps the bend direction.",
    {
        "armature": string("Armature object."),
        "bone": string("Last bone of the chain, such as the shin.", max_length=63),
        "chain_length": integer("Bones in the chain, counted up from bone.", 1, 16, 2),
        "target_bone": string("Control bone the chain reaches for; made at the bone's tail when it does not exist.", max_length=63),
        "target_object": string("Object the chain reaches for, instead of a target bone."),
        "pole": boolean("Add a pole target in front of the middle joint so the knee or elbow bends the way the rest pose does.", True),
        "pole_bone": string("Pole control bone; made when it does not exist.", max_length=63),
        "pole_distance": length("How far the pole sits from the middle joint, in metres. Default: half the chain length."),
        "control_parent": string("Parent of new control bones. Default: the template's Root bone, or the top bone above the chain.", max_length=63),
    },
    ["armature", "bone"],
    family="rigging",
    intents=("leg IK with a knee pole", "make the hand reach a target", "inverse kinematics on the arm"),
    nearest=(("bone_constraint", "for copy rotation, damped track or limit rotation"),),
)
def ik_chain(ctx, args):
    armature = get_armature(args["armature"])
    chain = chain_of(armature, args["bone"], args["chain_length"])
    if "target_bone" in args and "target_object" in args:
        raise bad_args("give target_bone or target_object, not both")
    if len(armature.pose.bones[args["bone"]].constraints) >= MAX_CONSTRAINTS:
        raise bad_args(f"{args['bone']} already has {MAX_CONSTRAINTS} constraints")
    tip, base = chain[0], chain[-1]
    span = sum(bone.length for bone in chain)
    parent = control_parent(armature, args.get("control_parent"), chain)
    new_bones = []
    target_object = get_object(args["target_object"]) if "target_object" in args else None
    target_name = None
    if target_object is None:
        target_name = args.get("target_bone", f"{tip.name}_IK")
        if target_name not in armature.data.bones:
            head = to_world(armature, tip.tail_local)
            new_bones.append(control_bone(target_name, head, head + (to_world(armature, tip.tail_local) - to_world(armature, tip.head_local)).normalized() * 0.25 * tip.length, parent))
    pole_name = None
    if args["pole"]:
        if args["chain_length"] < 2:
            raise bad_args("a pole needs a chain of at least two bones")
        pole_name = args.get("pole_bone", f"{tip.name}_Pole")
        if pole_name not in armature.data.bones:
            middle = chain[-2].head_local
            bend = bend_direction(base.head_local, middle, tip.tail_local)
            point = to_world(armature, middle + bend * args.get("pole_distance", 0.5 * span))
            new_bones.append(control_bone(pole_name, point, point + Vector((0.0, 0.0, 0.1 * span)), parent))
    if new_bones:
        add_bones(ctx, armature, new_bones)
    constraint = armature.pose.bones[tip.name].constraints.new("IK")
    constraint.name = f"IK {target_name or target_object.name}"
    constraint.chain_count = args["chain_length"]
    constraint.use_tail = True
    if target_object is not None:
        constraint.target = target_object
    else:
        constraint.target = armature
        constraint.subtarget = target_name
    if pole_name is not None:
        constraint.pole_target = armature
        constraint.pole_subtarget = pole_name
        constraint.pole_angle = pole_angle(armature.data.bones[base.name], armature.data.bones[tip.name], armature.data.bones[pole_name].head_local)
        settle_pole(ctx, armature, constraint, chain)
    ctx.view_layer.update()
    return {
        "armature": armature.name,
        "bone": tip.name,
        "constraint": constraint.name,
        "chain": [bone.name for bone in reversed(chain)],
        "target": target_name or target_object.name,
        "pole": pole_name,
        "pole_angle": rounded(math.degrees(constraint.pole_angle), 4) if pole_name else None,
        "created": [bone["name"] for bone in new_bones],
        "reach_error": rounded(reach_error(armature, tip.name, target_name, target_object)),
    }


def rest_drift(ctx, armature, chain):
    ctx.view_layer.update()
    worst = 0.0
    for bone in chain:
        pose_bone = armature.pose.bones[bone.name]
        worst = max(worst, (pose_bone.head - bone.head_local).length, (pose_bone.tail - bone.tail_local).length)
    return worst


def settle_pole(ctx, armature, constraint, chain):
    if rest_drift(ctx, armature, chain) < POLE_TOLERANCE:
        return
    best = min(range(-180, 180, 5), key=lambda degrees: drift_at(ctx, armature, constraint, chain, math.radians(degrees)))
    angle = math.radians(best)
    step = math.radians(2.5)
    while step > 1e-6:
        angle = min((angle - step, angle, angle + step), key=lambda value: drift_at(ctx, armature, constraint, chain, value))
        step /= 2
    constraint.pole_angle = angle


def drift_at(ctx, armature, constraint, chain, angle):
    constraint.pole_angle = angle
    return rest_drift(ctx, armature, chain)


def control_bone(name, head, tail, parent):
    spec = {"name": name, "head": list(head), "tail": list(tail), "deform": False}
    if parent:
        spec["parent"] = parent
    return spec


def reach_error(armature, tip, target_name, target_object):
    pose_tip = armature.matrix_world @ armature.pose.bones[tip].tail
    goal = target_object.matrix_world.translation if target_object is not None else armature.matrix_world @ armature.pose.bones[target_name].head
    return (pose_tip - goal).length


@command(
    "bone_constraint",
    "Add a bone constraint for posing: copy rotation or location, damped track, or limit rotation in degrees, with a target bone or object and influence.",
    {
        "armature": string("Armature object."),
        "bone": string("Bone that gets the constraint.", max_length=63),
        "type": string("Constraint kind.", list(KINDS)),
        "name": string("Constraint name. Default: from the type.", max_length=63),
        "target_bone": string("Target bone in the same armature.", max_length=63),
        "target_object": string("Target object."),
        "influence": number("How strongly it acts, 0 to 1.", 0.0, 1.0, 1.0),
        "axes": array(string("Axis.", ["x", "y", "z"]), "copy rotation, copy location, limit rotation: the axes it acts on. Default all three.", 1, 3),
        "min": vector3("limit rotation: lowest angles per axis in degrees.", [-180.0, -180.0, -180.0], -360.0, 360.0),
        "max": vector3("limit rotation: highest angles per axis in degrees.", [180.0, 180.0, 180.0], -360.0, 360.0),
        "track_axis": string("damped track: the bone axis that points at the target.", list(TRACK_AXES), "y"),
        "mix": string("copy rotation: how the copied rotation joins the bone's own.", list(MIXES), "replace"),
        "space": string("Space of owner and target: world, pose or local.", list(SPACES)),
    },
    ["armature", "bone", "type"],
    family="rigging",
    intents=("keep the head looking at a target", "limit how far the elbow bends", "copy the rotation of another bone"),
    nearest=(("ik_chain", "for a limb that reaches a target"),),
)
def bone_constraint(ctx, args):
    armature = get_armature(args["armature"])
    require_bone(armature, args["bone"])
    kind = args["type"]
    pose_bone = armature.pose.bones[args["bone"]]
    if len(pose_bone.constraints) >= MAX_CONSTRAINTS:
        raise bad_args(f"{args['bone']} already has {MAX_CONSTRAINTS} constraints")
    if "target_bone" in args and "target_object" in args:
        raise bad_args("give target_bone or target_object, not both")
    needs_target = kind != "limit_rotation"
    if needs_target and "target_bone" not in args and "target_object" not in args:
        raise bad_args(f"{kind} needs target_bone or target_object")
    if not needs_target and ("target_bone" in args or "target_object" in args):
        raise bad_args("limit_rotation takes no target")
    if "target_bone" in args:
        require_bone(armature, args["target_bone"])
        if args["target_bone"] == args["bone"]:
            raise bad_args("a bone cannot target itself")
    target_object = get_object(args["target_object"]) if "target_object" in args else None
    axes = set(args.get("axes", ["x", "y", "z"]))
    constraint = pose_bone.constraints.new(KINDS[kind])
    constraint.name = args.get("name", kind.replace("_", " ").title())
    constraint.influence = args["influence"]
    if needs_target:
        constraint.target = target_object or armature
        if "target_bone" in args:
            constraint.subtarget = args["target_bone"]
    if kind in ("copy_rotation", "copy_location"):
        constraint.use_x, constraint.use_y, constraint.use_z = ("x" in axes, "y" in axes, "z" in axes)
    if kind == "copy_rotation":
        constraint.mix_mode = MIXES[args["mix"]]
    if kind == "damped_track":
        constraint.track_axis = TRACK_AXES[args["track_axis"]]
    if kind == "limit_rotation":
        for index, axis in enumerate("xyz"):
            low, high = args["min"][index], args["max"][index]
            if low > high:
                raise bad_args(f"limit_rotation min {axis} is above max {axis}")
            setattr(constraint, f"use_limit_{axis}", axis in axes)
            setattr(constraint, f"min_{axis}", math.radians(low))
            setattr(constraint, f"max_{axis}", math.radians(high))
        constraint.owner_space = "LOCAL"
    if "space" in args:
        constraint.owner_space = SPACES[args["space"]]
        if needs_target:
            constraint.target_space = SPACES[args["space"]]
    ctx.view_layer.update()
    return {
        "armature": armature.name,
        "bone": pose_bone.name,
        "constraint": constraint.name,
        "type": kind,
        "influence": constraint.influence,
        "constraints": [item.name for item in pose_bone.constraints],
        "pose_head": vec(armature.matrix_world @ pose_bone.head),
        "pose_tail": vec(armature.matrix_world @ pose_bone.tail),
    }
