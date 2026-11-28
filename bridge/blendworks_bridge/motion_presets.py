"""Motion presets: role checks, sampling and idle poses for clips."""

import math

from mathutils import Matrix, Vector


from .clips import channels, curve, refresh_tracks, set_cyclic, set_range, write_samples
from .errors import bad_args
from .gaits import HumanoidWalk, Plan, QuadrupedGait, leg_length, plan_for
from .posing import UP, Poser, basis_channels, rotation

HUMANOID_LEGS = tuple(f"{side}{part}" for side in ("left", "right") for part in ("UpperLeg", "LowerLeg", "Foot", "Toes"))
QUADRUPED_LEGS = tuple(f"{side}{end}{part}" for side in ("left", "right") for end in ("Front", "Back") for part in ("UpperLeg", "LowerLeg", "Foot"))
REQUIRED_ROLES = {"humanoid": ("hips",) + HUMANOID_LEGS, "quadruped": ("hips", "chest") + QUADRUPED_LEGS}
PROP_ROLES = {"open": ("lid",), "spin": ("wheel",), "pump": ("rod",), "turn": ("lid", "wheel", "rod")}
PRESETS = ("walk", "trot", "idle", "open", "spin", "turn", "pump")
MAX_BOB = 0.08
STILL = 1e-6


def check_roles(roles, kind):
    missing = [role for role in REQUIRED_ROLES[kind] if role not in roles]
    if missing:
        raise bad_args(f"the {kind} preset needs bones for these roles: {', '.join(missing)}; rig with rig_template or pass bone_map")


def sample(poser, frame, count, root_motion, root):
    rows = []
    for index in range(count + 1):
        frame(index / count)
        rows.append({name: poser.basis(name) for name in poser.rest})
    for name in poser.rest:
        if root_motion and name == root:
            continue
        rows[-1][name] = rows[0][name].copy()
    return rows


def write_rows(armature, action, rows, start, bones, cyclic, travelling=()):
    bag, _ = channels(action, armature)
    frames = [start + index for index in range(len(rows))]
    for name in bones:
        pose_bone = armature.pose.bones[name]
        pose_bone.rotation_mode = "QUATERNION"
        locations = []
        rotations = []
        previous = None
        for row in rows:
            location, quaternion, _ = basis_channels(row[name], previous)
            previous = quaternion
            locations.append(location)
            rotations.append(quaternion)
        group = name
        for index in range(3):
            write_samples(curve(bag, f'pose.bones["{name}"].location', index, group), frames, [value[index] for value in locations])
        for index in range(4):
            write_samples(curve(bag, f'pose.bones["{name}"].rotation_quaternion', index, group), frames, [value[index] for value in rotations])
    set_range(action, start, start + len(rows) - 1)
    set_cyclic(action, cyclic)
    if cyclic:
        for name in travelling:
            for index in range(3):
                for modifier in curve(bag, f'pose.bones["{name}"].location', index, name).modifiers:
                    modifier.mode_before = "REPEAT_OFFSET"
                    modifier.mode_after = "REPEAT_OFFSET"
    refresh_tracks(action, [armature])


def moving_bones(rows, names):
    identity = Matrix.Identity(4)
    moved = []
    for name in names:
        if any(max(abs(a - b) for row_a, row_b in zip(row[name], identity) for a, b in zip(row_a, row_b)) > STILL for row in rows):
            moved.append(name)
    return moved


def gait(armature, roles, kind, preset, fps, args):
    poser = Poser(armature)
    check_roles(roles, kind)
    leg = leg_length(poser, roles, kind)
    plan = plan_for(kind, "walk" if kind == "humanoid" else preset, leg, fps, args)
    mover = HumanoidWalk(poser, roles, plan, args.get("heel_angle", 22.0)) if kind == "humanoid" else QuadrupedGait(poser, roles, plan, preset)
    if "bob" not in args:
        plan.bob = 0.0
        plan.bob = min(0.98 * mover.drop(), MAX_BOB * leg)
    drop = mover.drop()
    if drop > 0.3 * leg:
        raise bad_args(f"the stride of {plan.stride:.3f} m is too long for legs of {leg:.3f} m: the hips would sink {drop:.3f} m")
    rows = sample(poser, lambda phase: mover.frame(phase, drop), plan.frames, plan.root_motion, roles.get("root"))
    info = plan.describe()
    info.update({"leg_length": round(leg, 6), "hip_drop": round(drop, 6), "bob": round(plan.bob, 6)})
    return rows, plan.frames, info


def still_plan(fps):
    return Plan(0.0, 1, fps, 0.6, 0.0, False, 0.0, 0.0, 0.0)


def humanoid_idle(poser, roles, frames, fps):
    legs = HumanoidWalk(poser, roles, still_plan(fps), 0.0)
    leg = leg_length(poser, roles, "humanoid")

    def frame(phase):
        wave = 2.0 * math.pi * phase
        poser.clear()
        hips = roles["hips"]
        base = poser.follow(hips)
        offset = Vector((0.012 * leg * math.sin(wave), 0.0, -0.012 * leg - 0.006 * leg * (1.0 - math.cos(2.0 * wave)) / 2.0))
        poser.place(hips, base.translation + offset, rotation((0.0, 1.0, 0.0), -1.2 * math.sin(wave)).to_3x3() @ base.to_3x3())
        for role, amount in (("spine", 0.6), ("chest", 1.2)):
            if role in roles:
                poser.turn(roles[role], rotation((1.0, 0.0, 0.0), -amount * math.sin(wave + 0.5)) @ rotation((0.0, 1.0, 0.0), 0.8 * math.sin(wave)))
        if "head" in roles:
            head = roles["head"]
            look = rotation(UP, 7.0 * math.sin(wave)) @ rotation((1.0, 0.0, 0.0), 2.0 * math.sin(2.0 * wave))
            poser.place(head, poser.follow(head).translation, look.to_3x3() @ poser.rest[head].to_3x3())
        legs.legs(0.0)
        for side, sign in (("left", 1.0), ("right", -1.0)):
            upper, lower = roles.get(side + "UpperArm"), roles.get(side + "LowerArm")
            if upper is None or lower is None:
                continue
            hang = Vector((sign * math.sin(math.radians(9.0)), 0.0, -math.cos(math.radians(9.0))))
            sway = 3.0 * math.sin(wave + 1.0)
            poser.aim(upper, rotation((1.0, 0.0, 0.0), -sway).to_3x3() @ hang)
            poser.aim(lower, rotation((1.0, 0.0, 0.0), -(sway + 12.0)).to_3x3() @ hang)

    return frame


def quadruped_idle(poser, roles, frames, fps):
    legs = QuadrupedGait(poser, roles, Plan(0.0, 1, fps, 0.7, 0.0, False, 0.0, 0.0, 0.0), "walk")
    leg = leg_length(poser, roles, "quadruped")

    def frame(phase):
        wave = 2.0 * math.pi * phase
        poser.clear()
        hips = roles["hips"]
        base = poser.follow(hips)
        poser.place(hips, base.translation + Vector((0.0, 0.0, -0.01 * leg - 0.008 * leg * (1.0 - math.cos(wave)) / 2.0)), base.to_3x3())
        if "chest" in roles:
            poser.turn(roles["chest"], rotation((1.0, 0.0, 0.0), 1.2 * math.sin(2.0 * wave)))
        if "neck" in roles:
            poser.turn(roles["neck"], rotation(UP, 6.0 * math.sin(wave)))
        if "head" in roles:
            head = roles["head"]
            look = rotation(UP, 10.0 * math.sin(wave)) @ rotation((1.0, 0.0, 0.0), 3.0 * math.sin(2.0 * wave + 0.4))
            poser.place(head, poser.follow(head).translation, look.to_3x3() @ poser.rest[head].to_3x3())
        for role, lag, amount in (("tail", 0.0, 14.0), ("tailTip", 0.8, 18.0)):
            if role in roles:
                poser.turn(roles[role], rotation(UP, amount * math.sin(2.0 * wave - lag)))
        legs.legs(0.0)

    return frame


def idle(armature, roles, kind, fps, args):
    poser = Poser(armature)
    check_roles(roles, kind)
    frames = args.get("frames", round(3.0 * fps))
    builder = humanoid_idle if kind == "humanoid" else quadruped_idle
    rows = sample(poser, builder(poser, roles, frames, fps), frames, False, None)
    return rows, frames, {"frames": frames, "seconds": round(frames / fps, 6)}


def lid_sign(poser, bone, axis):
    tail = poser.rest_tail(bone)
    head = poser.rest_head(bone)
    moved = (rotation(axis, 1.0).to_3x3() @ (tail - head)).z - (tail - head).z
    return 1.0 if moved >= 0 else -1.0


def prop_profile(preset, args, phase):
    loop = args["loop"]
    if preset == "open":
        if not loop:
            return smooth_step(phase)
        if phase < 0.4:
            return smooth_step(phase / 0.4)
        if phase < 0.6:
            return 1.0
        return smooth_step((1.0 - phase) / 0.4)
    if preset == "spin":
        return phase
    return (1.0 - math.cos(2.0 * math.pi * phase)) / 2.0 if loop else smooth_step(phase)


def smooth_step(value):
    value = min(max(value, 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def prop_motion(armature, roles, preset, fps, args, axis):
    poser = Poser(armature)
    bone = args.get("bone") or next((roles[role] for role in PROP_ROLES[preset] if role in roles), None)
    if bone is None:
        raise bad_args(f"the {preset} preset needs a bone: give bone, or rig with the {'hinge' if preset == 'open' else 'wheel' if preset == 'spin' else 'piston'} template")
    if bone not in poser.rest:
        raise bad_args(f"{armature.name} has no bone named {bone}")
    frames = args.get("frames", round(2.0 * fps))
    loop = args["loop"] or preset == "spin"
    amount = {"open": args.get("angle", 100.0), "turn": args.get("angle", 90.0), "spin": 360.0 * args.get("turns", 1.0), "pump": args.get("distance", 0.1)}[preset]
    sign = lid_sign(poser, bone, axis) if preset == "open" else 1.0

    def frame(phase):
        poser.clear()
        share = prop_profile(preset, dict(args, loop=loop), phase)
        if preset == "pump":
            poser.set(bone, Matrix.Translation(axis * amount * share) @ poser.follow(bone))
        else:
            poser.turn(bone, rotation(axis, sign * amount * share))

    rows = sample(poser, frame, frames, not loop, bone)
    return rows, frames, {"frames": frames, "seconds": round(frames / fps, 6), "bone": bone, "amount": amount, "loop": loop, "axis": [round(value, 6) for value in axis]}
