"""Rig layouts: landmarks and bone points for humanoid and quadruped rigs."""

import math

from mathutils import Vector

from .errors import bad_args

HUMANOID_POINTS = {
    "hips": (0.0, 0.0, 0.53),
    "spine": (0.0, 0.0, 0.61),
    "chest": (0.0, 0.0, 0.70),
    "neck": (0.0, 0.0, 0.83),
    "head": (0.0, 0.0, 0.875),
    "head_top": (0.0, 0.0, 1.0),
    "left_clavicle": (0.02, 0.0, 0.815),
    "left_hip": (0.055, 0.0, 0.51),
    "left_knee": (0.055, -0.012, 0.285),
    "left_ankle": (0.055, 0.0, 0.05),
    "left_ball": (0.055, -0.09, 0.015),
    "left_toe": (0.055, -0.14, 0.015),
}
HUMANOID_SHOULDER = (0.105, 0.0, 0.81)
HUMANOID_ARM = (0.175, 0.145, 0.095)
POSE_ANGLES = {"a": 45.0, "t": 0.0}
A_POSE_RANGE = (25.0, 70.0)
HUMANOID_ARM_POINTS = ("left_shoulder", "left_elbow", "left_wrist", "left_hand_tip")

QUADRUPED_POINTS = {
    "head_tip": (0.0, 0.0, 0.78),
    "head": (0.0, 0.13, 0.88),
    "neck": (0.0, 0.25, 0.73),
    "chest": (0.0, 0.31, 0.66),
    "spine": (0.0, 0.55, 0.65),
    "hips": (0.0, 0.79, 0.64),
    "tail": (0.0, 0.91, 0.70),
    "tail_tip": (0.0, 1.0, 0.74),
    "left_front_shoulder": (0.6, 0.30, 0.56),
    "left_front_elbow": (0.6, 0.34, 0.36),
    "left_front_wrist": (0.6, 0.30, 0.11),
    "left_front_paw": (0.6, 0.27, 0.0),
    "left_back_hip": (0.6, 0.79, 0.56),
    "left_back_knee": (0.6, 0.74, 0.35),
    "left_back_hock": (0.6, 0.85, 0.15),
    "left_back_paw": (0.6, 0.83, 0.0),
}

HUMANOID_CHAIN = (
    ("Root", "root", "@root", "@root_tail", None, False, False),
    ("Hips", "hips", "hips", "spine", "Root", False, True),
    ("Spine", "spine", "spine", "chest", "Hips", True, True),
    ("Chest", "chest", "chest", "neck", "Spine", True, True),
    ("Neck", "neck", "neck", "head", "Chest", True, True),
    ("Head", "head", "head", "head_top", "Neck", True, True),
)
HUMANOID_SIDE = (
    ("Shoulder", "Shoulder", "clavicle", "shoulder", "Chest", False),
    ("UpperArm", "UpperArm", "shoulder", "elbow", "Shoulder", True),
    ("LowerArm", "LowerArm", "elbow", "wrist", "UpperArm", True),
    ("Hand", "Hand", "wrist", "hand_tip", "LowerArm", True),
    ("UpperLeg", "UpperLeg", "hip", "knee", "Hips", False),
    ("LowerLeg", "LowerLeg", "knee", "ankle", "UpperLeg", True),
    ("Foot", "Foot", "ankle", "ball", "LowerLeg", True),
    ("Toes", "Toes", "ball", "toe", "Foot", True),
)
QUADRUPED_CHAIN = (
    ("Root", "root", "@root", "@root_tail", None, False, False),
    ("Hips", "hips", "hips", "spine", "Root", False, True),
    ("Spine", "spine", "spine", "chest", "Hips", True, True),
    ("Chest", "chest", "chest", "neck", "Spine", True, True),
    ("Neck", "neck", "neck", "head", "Chest", True, True),
    ("Head", "head", "head", "head_tip", "Neck", True, True),
    ("Tail", "tail", "hips", "tail", "Hips", False, True),
    ("TailTip", "tailTip", "tail", "tail_tip", "Tail", True, True),
)
QUADRUPED_SIDE = (
    ("FrontUpperLeg", "FrontUpperLeg", "front_shoulder", "front_elbow", "Chest", False),
    ("FrontLowerLeg", "FrontLowerLeg", "front_elbow", "front_wrist", "FrontUpperLeg", True),
    ("FrontFoot", "FrontFoot", "front_wrist", "front_paw", "FrontLowerLeg", True),
    ("BackUpperLeg", "BackUpperLeg", "back_hip", "back_knee", "Hips", False),
    ("BackLowerLeg", "BackLowerLeg", "back_knee", "back_hock", "BackUpperLeg", True),
    ("BackFoot", "BackFoot", "back_hock", "back_paw", "BackLowerLeg", True),
)
PROP_POINTS = {
    "hinge": ("base", "hinge", "tip"),
    "piston": ("base", "joint", "top"),
    "wheel": ("base", "centre", "axle_end"),
}
PROP_BONES = {"hinge": ("Base", "Lid"), "piston": ("Base", "Rod"), "wheel": ("Base", "Wheel")}
TEMPLATES = ("humanoid", "quadruped", "hinge", "piston", "wheel")


class Frame:
    def __init__(self, low, high):
        self.low = Vector(low)
        self.high = Vector(high)
        self.size = self.high - self.low
        self.centre = (self.low + self.high) / 2
        if min(self.size) < 0:
            raise bad_args("the fitting bounds have a negative size")
        if self.size.z <= 1e-3:
            raise bad_args("the fitting bounds are flat; give a mesh with some height or landmarks")


def landmark_names(template):
    if template == "humanoid":
        names = set(HUMANOID_POINTS) | set(HUMANOID_ARM_POINTS)
    elif template == "quadruped":
        names = set(QUADRUPED_POINTS)
    else:
        return set(PROP_POINTS[template])
    names |= {"right" + name[4:] for name in names if name.startswith("left")}
    return names


def check_landmarks(template, landmarks):
    allowed = landmark_names(template)
    unknown = sorted(set(landmarks) - allowed)
    if unknown:
        raise bad_args(f"unknown {template} landmark(s): {', '.join(unknown)}; known: {', '.join(sorted(allowed))}")


def humanoid_points(frame, landmarks, pose, hip_spread):
    height = frame.size.z
    points = {}
    for name, (x, y, z) in HUMANOID_POINTS.items():
        spread = hip_spread if hip_spread is not None and name.startswith("left_") and name != "left_clavicle" else x * height
        points[name] = Vector((frame.centre.x + spread, frame.centre.y + y * height, frame.low.z + z * height))
    shoulder = Vector((frame.centre.x + HUMANOID_SHOULDER[0] * height, frame.centre.y, frame.low.z + HUMANOID_SHOULDER[2] * height))
    shoulder = Vector(landmarks.get("left_shoulder", shoulder))
    lengths = [part * height for part in HUMANOID_ARM]
    angle, lengths = arm_fit(pose, frame.high.x - shoulder.x, lengths)
    direction = Vector((math.cos(angle), 0.0, -math.sin(angle)))
    points["left_shoulder"] = shoulder
    points["left_elbow"] = shoulder + direction * lengths[0]
    points["left_wrist"] = points["left_elbow"] + direction * lengths[1]
    points["left_hand_tip"] = points["left_wrist"] + direction * lengths[2]
    return points


def arm_fit(pose, reach, lengths):
    total = sum(lengths)
    if pose == "a" and reach > 0:
        angle = math.acos(min(max(reach / total, math.cos(math.radians(A_POSE_RANGE[1]))), math.cos(math.radians(A_POSE_RANGE[0]))))
    else:
        angle = math.radians(POSE_ANGLES[pose])
    span = total * math.cos(angle)
    if reach > 0 and 0.6 < reach / span < 1.4:
        lengths = [part * reach / span for part in lengths]
    return angle, lengths


def quadruped_points(frame, leg_spread):
    points = {}
    for name, (x, y, z) in QUADRUPED_POINTS.items():
        spread = leg_spread if leg_spread is not None and name.startswith("left_") else x * frame.size.x / 2
        points[name] = Vector((frame.centre.x + spread, frame.low.y + y * frame.size.y, frame.low.z + z * frame.size.z))
    return points


def mirror_left(points, frame, landmarks):
    for name in list(points):
        if name.startswith("left_"):
            right = "right_" + name[5:]
            point = points[name]
            points[right] = Vector(landmarks[right]) if right in landmarks else Vector((2 * frame.centre.x - point.x, point.y, point.z))
    return points


def body_layout(chain, side, points, frame, forward_tail):
    root = Vector((frame.centre.x, frame.centre.y, frame.low.z))
    points["@root"] = root
    points["@root_tail"] = root + Vector((0.0, -1.0, 0.0)) * forward_tail
    bones = []
    roles = {}
    for name, role, head, tail, parent, connect, deform in chain:
        bones.append(bone_spec(name, points[head], points[tail], parent, connect, deform))
        roles[role] = name
    for prefix, side_name in (("left", "Left"), ("right", "Right")):
        for suffix, role_suffix, head, tail, parent, connect in side:
            parent_name = parent if parent in ("Chest", "Hips") else side_name + parent
            name = side_name + suffix
            bones.append(bone_spec(name, points[f"{prefix}_{head}"], points[f"{prefix}_{tail}"], parent_name, connect, True))
            roles[prefix + role_suffix] = name
    return bones, roles


def bone_spec(name, head, tail, parent, connect, deform):
    spec = {"name": name, "head": list(head), "tail": list(tail), "roll": 0.0, "connect": connect, "deform": deform}
    if parent is not None:
        spec["parent"] = parent
    return spec


def humanoid(frame, landmarks, pose, hip_spread=None):
    points = humanoid_points(frame, landmarks, pose, hip_spread)
    points.update({name: Vector(value) for name, value in landmarks.items() if not name.startswith("right_")})
    points = mirror_left(points, frame, landmarks)
    return body_layout(HUMANOID_CHAIN, HUMANOID_SIDE, points, frame, 0.12 * frame.size.z)


def quadruped(frame, landmarks, leg_spread=None):
    points = quadruped_points(frame, leg_spread)
    points.update({name: Vector(value) for name, value in landmarks.items() if not name.startswith("right_")})
    points = mirror_left(points, frame, landmarks)
    return body_layout(QUADRUPED_CHAIN, QUADRUPED_SIDE, points, frame, 0.15 * frame.size.y)


def prop_defaults(template, frame, axis):
    low, high, centre = frame.low, frame.high, frame.centre
    if template == "hinge":
        hinge_z = low.z + 0.62 * frame.size.z
        return {"base": Vector((centre.x, centre.y, low.z)), "hinge": Vector((centre.x, high.y, hinge_z)), "tip": Vector((centre.x, low.y, hinge_z))}
    if template == "piston":
        return {"base": low_point(frame, axis), "joint": centre.copy(), "top": centre + axis * (abs(axis.dot(frame.size)) / 2)}
    return {"base": Vector((centre.x, centre.y, low.z)), "centre": centre.copy(), "axle_end": centre + axis * max(abs(axis.dot(frame.size)) / 2, 0.25 * max(frame.size))}


def low_point(frame, axis):
    return frame.centre - axis * (abs(axis.dot(frame.size)) / 2)


def prop(template, frame, landmarks, axis):
    points = prop_defaults(template, frame, axis)
    points.update({name: Vector(value) for name, value in landmarks.items()})
    base_name, moving_name = PROP_BONES[template]
    base, joint, end = (points[name] for name in PROP_POINTS[template])
    if (joint - base).length < 1e-4:
        base = joint - Vector((0.0, 0.0, max(frame.size.z, 0.01) * 0.25))
    bones = [
        bone_spec(base_name, base, joint, None, False, True),
        bone_spec(moving_name, joint, end, base_name, False, True),
    ]
    return bones, {"base": base_name, template_role(template): moving_name}


def template_role(template):
    return {"hinge": "lid", "piston": "rod", "wheel": "wheel"}[template]


def ground_height(bones, template, frame):
    if template in ("humanoid", "quadruped"):
        return frame.low.z
    return min(min(bone["head"][2], bone["tail"][2]) for bone in bones)
