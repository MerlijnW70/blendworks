import math

SKIN = [0.86, 0.63, 0.5]
COLOURS = {
    "skin": SKIN,
    "shirt": [0.16, 0.36, 0.62],
    "trousers": [0.2, 0.21, 0.26],
    "shoes": [0.12, 0.08, 0.06],
    "dark": [0.03, 0.03, 0.035],
    "fur": [0.78, 0.4, 0.14],
    "cream": [0.93, 0.86, 0.74],
    "wood": [0.45, 0.27, 0.12],
    "iron": [0.25, 0.25, 0.27],
}


def materials(cmd, names):
    for name in names:
        cmd("add_material", name=name, base_color=COLOURS[name], roughness=0.65 if name != "iron" else 0.4, metallic=0.8 if name == "iron" else 0.0)


def mix(start, end, share):
    return [start[axis] + (end[axis] - start[axis]) * share for axis in range(3)]


def along(points, steps, rounding=0.3):
    corners = [list(points[0])]
    for before, joint, after in zip(points, points[1:], points[2:]):
        entry, leave = mix(joint, before, rounding), mix(joint, after, rounding)
        for step in range(steps + 1):
            share = step / steps
            corners.append(mix(mix(entry, joint, share), mix(joint, leave, share), share))
    corners.append(list(points[-1]))
    path = [corners[0]]
    for start, end in zip(corners, corners[1:]):
        length = sum((end[axis] - start[axis]) ** 2 for axis in range(3)) ** 0.5
        count = max(1, round(length / 0.04))
        path.extend(mix(start, end, step / count) for step in range(1, count + 1))
    return path


def limb(cmd, name, joints, radius, taper, material, steps=6):
    cmd("sweep", name=name, preset="circle", radius=radius, segments=16, waypoints=along(joints, steps), scale_end=taper, shading="smooth")
    cmd("assign_material", name=name, material=material)


def ball(cmd, name, location, radius, scale, material, rotation=(0.0, 0.0, 0.0)):
    cmd("add_primitive", type="sphere", name=name, radius=radius, segments=24, rings=12, location=list(location), rotation=list(rotation))
    cmd("transform", name=name, scale=list(scale))
    cmd("apply_transform", name=name)
    cmd("shade_smooth", name=name)
    cmd("assign_material", name=name, material=material)


def block(cmd, name, location, size, material, bevel=0.0, cuts=0):
    cmd("add_primitive", type="cube", name=name, size=1.0, location=list(location))
    cmd("transform", name=name, scale=list(size))
    cmd("apply_transform", name=name)
    if cuts:
        cmd("subdivide", name=name, cuts=cuts)
    if bevel:
        cmd("bevel", name=name, width=bevel, segments=2)
    cmd("assign_material", name=name, material=material)


ARM_ANGLE = math.radians(45.0)
SHOULDER = (0.2, 0.0, 1.38)
UPPER_ARM = 0.27
FOREARM = 0.25


def arm_point(side, distance):
    return [side * (SHOULDER[0] + distance * math.cos(ARM_ANGLE)), 0.0, SHOULDER[2] - distance * math.sin(ARM_ANGLE)]


HERO_LANDMARKS = {
    "hips": [0.0, 0.0, 0.93],
    "spine": [0.0, 0.0, 1.06],
    "chest": [0.0, 0.0, 1.2],
    "neck": [0.0, 0.0, 1.44],
    "head": [0.0, 0.0, 1.53],
    "head_top": [0.0, 0.0, 1.76],
    "left_clavicle": [0.04, 0.0, 1.38],
    "left_shoulder": arm_point(1, 0.0),
    "left_elbow": arm_point(1, UPPER_ARM),
    "left_wrist": arm_point(1, UPPER_ARM + FOREARM),
    "left_hand_tip": arm_point(1, UPPER_ARM + FOREARM + 0.15),
    "left_hip": [0.1, 0.0, 0.92],
    "left_knee": [0.1, -0.02, 0.5],
    "left_ankle": [0.1, 0.0, 0.1],
    "left_ball": [0.1, -0.13, 0.03],
    "left_toe": [0.1, -0.21, 0.03],
}


def hero(cmd):
    materials(cmd, ("skin", "shirt", "trousers", "shoes", "dark"))
    torso = [[0.0, 0.84], [0.12, 0.85], [0.165, 0.92], [0.16, 1.02], [0.15, 1.1], [0.17, 1.24], [0.195, 1.34], [0.17, 1.41], [0.08, 1.46], [0.0, 1.47]]
    cmd("lathe", name="Torso", profile=torso, segments=28, shading="smooth")
    cmd("transform", name="Torso", scale=[1.0, 0.64, 1.0])
    cmd("apply_transform", name="Torso")
    cmd("subdivide", name="Torso", cuts=1)
    cmd("assign_material", name="Torso", material="shirt")
    block(cmd, "Belt", [0.0, 0.0, 0.92], [0.335, 0.215, 0.07], "trousers", bevel=0.02)
    cmd("add_primitive", type="cylinder", name="Neck", radius=0.05, depth=0.16, segments=16, location=[0.0, 0.0, 1.5])
    cmd("assign_material", name="Neck", material="skin")
    ball(cmd, "Head", [0.0, -0.005, 1.63], 0.12, [0.92, 1.0, 1.1], "skin")
    for side, label in ((1, "L"), (-1, "R")):
        hip = HERO_LANDMARKS["left_hip"]
        leg = [[side * hip[0], 0.0, 0.97], [side * hip[0], -0.02, 0.5], [side * hip[0], 0.0, 0.09]]
        limb(cmd, f"Leg{label}", leg, 0.072, 0.72, "trousers")
        block(cmd, f"Shoe{label}", [side * hip[0], -0.075, 0.045], [0.11, 0.27, 0.09], "shoes", bevel=0.02, cuts=2)
        arm = [arm_point(side, -0.02), arm_point(side, UPPER_ARM), arm_point(side, UPPER_ARM + FOREARM)]
        limb(cmd, f"Arm{label}", arm, 0.05, 0.78, "shirt")
        wrist = arm_point(side, UPPER_ARM + FOREARM + 0.06)
        ball(cmd, f"Hand{label}", wrist, 0.055, [0.75, 0.55, 1.15], "skin", rotation=(0.0, side * 45.0, 0.0))
        ball(cmd, f"Eye{label}", [side * 0.042, -0.108, 1.66], 0.019, [1.0, 0.6, 1.0], "dark")
    cmd("join", names=["Torso", "Belt", "Neck", "Head", "EyeL", "EyeR"])
    cmd("rename", name="Torso", new_name="HeroBody")
    cmd("join", names=["LegL", "LegR", "ShoeL", "ShoeR"])
    cmd("rename", name="LegL", new_name="HeroLegs")
    cmd("join", names=["ArmL", "ArmR", "HandL", "HandR"])
    cmd("rename", name="ArmL", new_name="HeroArms")
    meshes = ["HeroBody", "HeroLegs", "HeroArms"]
    landmarks = [{"name": name, "point": point} for name, point in HERO_LANDMARKS.items()]
    cmd("rig_template", template="humanoid", name="HeroRig", fit=meshes, landmarks=landmarks)
    head = [{"bone": "Head", "near": point} for point in ([0.0, -0.005, 1.63], [0.042, -0.11, 1.66], [-0.042, -0.11, 1.66])]
    cmd("skin_bind", meshes=["HeroBody"], armature="HeroRig", bones=["Hips", "Spine", "Chest", "Neck", "Head"], rigid=head, smooth=2)
    legs = ["Hips"] + [f"{side}{part}" for side in ("Left", "Right") for part in ("UpperLeg", "LowerLeg", "Foot", "Toes")]
    cmd("skin_bind", meshes=["HeroLegs"], armature="HeroRig", bones=legs, smooth=2)
    arms = ["Chest"] + [f"{side}{part}" for side in ("Left", "Right") for part in ("Shoulder", "UpperArm", "LowerArm", "Hand")]
    hands = [{"bone": f"{side}Hand", "near": arm_point(sign, UPPER_ARM + FOREARM + 0.14)} for side, sign in (("Left", 1), ("Right", -1))]
    cmd("skin_bind", meshes=["HeroArms"], armature="HeroRig", bones=arms, rigid=hands, smooth=2)
    return meshes, "HeroRig"


FOX_LANDMARKS = {
    "hips": [0.0, 0.2, 0.5],
    "spine": [0.0, 0.0, 0.5],
    "chest": [0.0, -0.2, 0.51],
    "neck": [0.0, -0.3, 0.58],
    "head": [0.0, -0.4, 0.7],
    "head_tip": [0.0, -0.58, 0.66],
    "tail": [0.0, 0.42, 0.56],
    "tail_tip": [0.0, 0.62, 0.66],
    "left_front_shoulder": [0.085, -0.22, 0.45],
    "left_front_elbow": [0.085, -0.19, 0.28],
    "left_front_wrist": [0.085, -0.22, 0.08],
    "left_front_paw": [0.085, -0.27, 0.0],
    "left_back_hip": [0.085, 0.22, 0.45],
    "left_back_knee": [0.085, 0.15, 0.29],
    "left_back_hock": [0.085, 0.27, 0.12],
    "left_back_paw": [0.085, 0.25, 0.0],
}


def fox(cmd):
    materials(cmd, ("fur", "cream", "dark"))
    body = [[0.0, 0.0], [0.08, 0.015], [0.12, 0.08], [0.13, 0.25], [0.14, 0.45], [0.13, 0.58], [0.07, 0.65], [0.0, 0.66]]
    cmd("lathe", name="Body", profile=body, segments=24, shading="smooth", rotation=[90.0, 0.0, 0.0], location=[0.0, 0.34, 0.5])
    cmd("transform", name="Body", scale=[0.85, 1.0, 1.0])
    cmd("apply_transform", name="Body")
    cmd("subdivide", name="Body", cuts=1)
    cmd("assign_material", name="Body", material="fur")
    limb(cmd, "Neck", [[0.0, -0.22, 0.5], [0.0, -0.4, 0.68]], 0.065, 0.85, "fur")
    ball(cmd, "Skull", [0.0, -0.41, 0.71], 0.09, [0.95, 1.05, 0.9], "fur")
    limb(cmd, "Snout", [[0.0, -0.45, 0.69], [0.0, -0.57, 0.665]], 0.045, 0.5, "cream", steps=3)
    ball(cmd, "Nose", [0.0, -0.578, 0.668], 0.018, [1.0, 1.0, 0.8], "dark")
    for side, label in ((1, "L"), (-1, "R")):
        cmd("add_primitive", type="cone", name=f"Ear{label}", radius=0.04, depth=0.1, segments=12, location=[side * 0.05, -0.39, 0.8], rotation=[-10.0, side * 15.0, 0.0])
        cmd("assign_material", name=f"Ear{label}", material="fur")
        ball(cmd, f"Eye{label}", [side * 0.045, -0.475, 0.73], 0.014, [1.0, 0.7, 1.0], "dark")
        x = side * 0.085
        front = [[x, -0.22, 0.5], [x, -0.19, 0.28], [x, -0.22, 0.08], [x, -0.245, 0.03]]
        back = [[x, 0.22, 0.5], [x, 0.15, 0.29], [x, 0.27, 0.12], [x, 0.255, 0.03]]
        limb(cmd, f"Front{label}", front, 0.042, 0.62, "fur")
        limb(cmd, f"Back{label}", back, 0.05, 0.55, "fur")
        ball(cmd, f"FrontPaw{label}", [x, -0.26, 0.022], 0.032, [1.0, 1.35, 0.7], "dark")
        ball(cmd, f"BackPaw{label}", [x, 0.245, 0.022], 0.032, [1.0, 1.35, 0.7], "dark")
    tail = [[0.0, 0.3, 0.53], [0.0, 0.42, 0.56], [0.0, 0.52, 0.6], [0.0, 0.63, 0.67]]
    limb(cmd, "Tail", tail, 0.05, 0.35, "fur")
    cmd("join", names=["Body", "Neck", "Skull", "Snout", "Nose", "EarL", "EarR", "EyeL", "EyeR", "Tail"])
    cmd("rename", name="Body", new_name="FoxBody")
    cmd("join", names=["FrontL", "FrontR", "BackL", "BackR", "FrontPawL", "FrontPawR", "BackPawL", "BackPawR"])
    cmd("rename", name="FrontL", new_name="FoxLegs")
    meshes = ["FoxBody", "FoxLegs"]
    landmarks = [{"name": name, "point": point} for name, point in FOX_LANDMARKS.items()]
    cmd("rig_template", template="quadruped", name="FoxRig", fit=meshes, landmarks=landmarks)
    head = [{"bone": "Head", "near": point} for point in ([0.0, -0.41, 0.71], [0.0, -0.57, 0.665], [0.0, -0.58, 0.668], [0.05, -0.39, 0.8], [-0.05, -0.39, 0.8], [0.045, -0.495, 0.735], [-0.045, -0.495, 0.735])]
    cmd("skin_bind", meshes=["FoxBody"], armature="FoxRig", bones=["Hips", "Spine", "Chest", "Neck", "Head", "Tail", "TailTip"], rigid=head, smooth=2)
    legs = ["Hips", "Chest"] + [f"{side}{end}{part}" for side in ("Left", "Right") for end in ("Front", "Back") for part in ("UpperLeg", "LowerLeg", "Foot")]
    paws = [{"bone": f"{side}{end}Foot", "near": [sign * 0.085, y - 0.06, -0.01]} for side, sign in (("Left", 1), ("Right", -1)) for end, y in (("Front", -0.26), ("Back", 0.245))]
    cmd("skin_bind", meshes=["FoxLegs"], armature="FoxRig", bones=legs, rigid=paws, smooth=2)
    return meshes, "FoxRig"


def chest(cmd):
    materials(cmd, ("wood", "iron"))
    block(cmd, "Box", [0.0, 0.0, 0.2], [0.8, 0.5, 0.4], "wood", bevel=0.015)
    block(cmd, "Lid", [0.0, 0.0, 0.46], [0.82, 0.52, 0.12], "wood", bevel=0.025)
    for index, x in enumerate((-0.3, 0.3)):
        block(cmd, f"Band{index}", [x, 0.0, 0.2], [0.05, 0.515, 0.405], "iron")
        block(cmd, f"LidBand{index}", [x, 0.0, 0.46], [0.05, 0.535, 0.125], "iron")
    block(cmd, "Lock", [0.0, -0.255, 0.34], [0.08, 0.03, 0.09], "iron", bevel=0.005)
    parts = ["Box", "Lid", "Band0", "Band1", "LidBand0", "LidBand1", "Lock"]
    cmd("join", names=parts)
    cmd("rename", name="Box", new_name="Chest")
    landmarks = [{"name": "base", "point": [0.0, 0.0, 0.0]}, {"name": "hinge", "point": [0.0, 0.26, 0.4]}, {"name": "tip", "point": [0.0, -0.26, 0.4]}]
    cmd("rig_template", template="hinge", name="ChestRig", fit=["Chest"], landmarks=landmarks)
    rigid = [{"bone": "Base", "near": point} for point in ([0.0, 0.0, -0.01], [-0.3, -0.26, 0.1], [0.3, -0.26, 0.1], [0.0, -0.3, 0.34])]
    rigid += [{"bone": "Lid", "near": point} for point in ([0.0, 0.0, 0.55], [-0.3, -0.29, 0.46], [0.3, -0.29, 0.46])]
    cmd("skin_bind", meshes=["Chest"], armature="ChestRig", weights="none", rigid=rigid)
    return "Chest", "ChestRig"
