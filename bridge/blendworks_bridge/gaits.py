import math

from mathutils import Matrix, Vector

from .errors import bad_args
from .posing import FORWARD, UP, bend_direction, leg_reach_height, rotation, two_bone

GRAVITY = 9.81
CYCLE_FACTOR = {"walk": 3.6, "trot": 2.2}
STRIDE_FACTOR = {"humanoid": {"walk": 1.0}, "quadruped": {"walk": 1.0, "trot": 1.5}}
STANCE = {"humanoid": {"walk": 0.6}, "quadruped": {"walk": 0.7, "trot": 0.5}}
QUADRUPED_PHASES = {
    "walk": {"leftBack": 0.0, "leftFront": 0.25, "rightBack": 0.5, "rightFront": 0.75},
    "trot": {"leftFront": 0.0, "rightBack": 0.0, "rightFront": 0.5, "leftBack": 0.5},
}
REACH_SLACK = 0.995
HEEL_OFF = 0.65
MIN_FRAMES = 8
MAX_FRAMES = 2_400


class Plan:
    def __init__(self, stride, frames, fps, stance, lift, root_motion, bob, sway, swing):
        self.stride = stride
        self.frames = frames
        self.fps = fps
        self.stance = stance
        self.lift = lift
        self.root_motion = root_motion
        self.bob = bob
        self.sway = sway
        self.swing = swing
        self.seconds = frames / fps
        self.speed = stride / self.seconds
        self.cadence = 120.0 / self.seconds

    def describe(self):
        return {
            "stride": round(self.stride, 6),
            "frames": self.frames,
            "seconds": round(self.seconds, 6),
            "speed": round(self.speed, 6),
            "cadence": round(self.cadence, 4),
            "stance": self.stance,
            "lift": round(self.lift, 6),
            "root_motion": self.root_motion,
        }


def cycle_frames(fps, leg, gait, stride, args):
    if "frames" in args:
        frames = args["frames"]
    elif "speed" in args:
        frames = round(stride / args["speed"] * fps)
    elif "cadence" in args:
        frames = round(120.0 / args["cadence"] * fps)
    else:
        frames = round(CYCLE_FACTOR[gait] * math.sqrt(leg / GRAVITY) * fps)
    if frames < MIN_FRAMES or frames > MAX_FRAMES:
        raise bad_args(f"the cycle would last {frames} frames; it must be {MIN_FRAMES} to {MAX_FRAMES}: change speed, cadence or frames")
    return int(frames)


def plan_for(kind, gait, leg, fps, args):
    stride = args.get("stride", STRIDE_FACTOR[kind][gait] * leg)
    frames = cycle_frames(fps, leg, gait, stride, args)
    lift = args.get("lift", (0.12 if kind == "humanoid" else 0.14) * leg)
    bob = args.get("bob", 0.03 * leg)
    return Plan(stride, frames, fps, STANCE[kind][gait], lift, args["root_motion"], bob, args.get("sway", 0.025 * leg), args.get("arm_swing", 22.0))


def hermite(start, end, slope, s):
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    return h00 * start + h10 * slope + h01 * end + h11 * slope


def smooth(value):
    value = min(max(value, 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def foot_path(phase, plan):
    span = plan.stride * plan.stance
    if phase < plan.stance:
        s = phase / plan.stance
        return span * (0.5 - s), 0.0, True, s
    s = (phase - plan.stance) / (1.0 - plan.stance)
    slope = -span * (1.0 - plan.stance) / plan.stance
    along = hermite(-span / 2, span / 2, slope, s)
    return along, plan.lift * math.sin(math.pi * s), False, s


class HumanoidWalk:
    def __init__(self, poser, roles, plan, heel_angle):
        self.poser = poser
        self.roles = roles
        self.plan = plan
        self.heel_angle = heel_angle
        self.sides = []
        for side in ("left", "right"):
            names = {part: roles[side + part] for part in ("UpperLeg", "LowerLeg", "Foot", "Toes")}
            hip = poser.rest_head(names["UpperLeg"])
            knee = poser.rest_head(names["LowerLeg"])
            ankle = poser.rest_head(names["Foot"])
            ball = poser.rest_head(names["Toes"])
            self.sides.append({
                "side": side,
                "names": names,
                "phase": 0.0 if side == "left" else 0.5,
                "pole": bend_direction(hip, knee, ankle),
                "upper": (knee - hip).length,
                "lower": (ankle - knee).length,
                "ankle": ankle,
                "ball": ball,
                "sign": 1.0 if side == "left" else -1.0,
            })

    def foot(self, side, phase):
        along, lift, stance, s = foot_path(phase, self.plan)
        ball = side["ball"] + FORWARD * along + UP * lift
        if stance:
            heel = self.heel_angle * smooth((s - HEEL_OFF) / (1.0 - HEEL_OFF)) if s > HEEL_OFF else 0.0
            toes = 0.0
        else:
            heel = self.heel_angle * (1.0 - smooth(s / 0.8))
            toes = heel * smooth(s / 0.35)
        turn = rotation((1.0, 0.0, 0.0), heel)
        ankle = ball + turn.to_3x3() @ (side["ankle"] - side["ball"])
        return ankle, ball, turn, rotation((1.0, 0.0, 0.0), toes)

    def body(self, phase, drop):
        poser = self.poser
        plan = self.plan
        roles = self.roles
        poser.clear()
        offset = FORWARD * plan.stride * phase if plan.root_motion else Vector()
        if "root" in roles:
            poser.set(roles["root"], Matrix.Translation(offset) @ poser.rest[roles["root"]])
        hips = roles["hips"]
        centre = (plan.stance - 0.5) / 2
        bob = -plan.bob * (1.0 + math.cos(4.0 * math.pi * (phase - centre))) / 2.0
        sway = plan.sway * math.sin(2.0 * math.pi * (phase - (plan.stance / 2 - 0.25)))
        yaw = -6.0 * math.cos(2.0 * math.pi * phase)
        turn = rotation(UP, yaw) @ rotation((1.0, 0.0, 0.0), 4.0)
        base = poser.follow(hips)
        place = base.translation + Vector((sway, 0.0, bob - drop))
        poser.place(hips, place, turn.to_3x3() @ base.to_3x3())
        for role, share in (("spine", -0.7), ("chest", -0.8)):
            if role in roles:
                poser.turn(roles[role], rotation(UP, yaw * share) @ rotation((1.0, 0.0, 0.0), -1.5))
        if "head" in roles:
            head = roles["head"]
            poser.place(head, poser.follow(head).translation, poser.rest[head].to_3x3())
        return yaw

    def legs(self, phase):
        poser = self.poser
        for side in self.sides:
            names = side["names"]
            leg_phase = (phase + side["phase"]) % 1.0
            ankle, ball, turn, toes = self.foot(side, leg_phase)
            shift = poser.pose(self.roles["root"]).translation - poser.rest[self.roles["root"]].translation if "root" in self.roles else Vector()
            ankle = ankle + shift
            ball = ball + shift
            hip = poser.follow(names["UpperLeg"]).translation
            pole = poser.pose(self.roles["hips"]).to_3x3() @ poser.rest[self.roles["hips"]].to_3x3().inverted() @ side["pole"]
            knee, _ = two_bone(hip, ankle, side["upper"], side["lower"], pole)
            poser.aim(names["UpperLeg"], knee - hip, hip)
            poser.aim(names["LowerLeg"], ankle - knee)
            poser.place(names["Foot"], ankle, turn.to_3x3() @ poser.rest[names["Foot"]].to_3x3())
            poser.place(names["Toes"], ball, toes.to_3x3() @ poser.rest[names["Toes"]].to_3x3())

    def arms(self, phase, yaw):
        poser = self.poser
        roles = self.roles
        for side, sign in (("left", 1.0), ("right", -1.0)):
            upper = roles.get(side + "UpperArm")
            lower = roles.get(side + "LowerArm")
            if upper is None or lower is None:
                continue
            forward = -sign * self.plan.swing * math.cos(2.0 * math.pi * phase)
            hang = Vector((sign * math.sin(math.radians(9.0)), 0.0, -math.cos(math.radians(9.0))))
            twist = rotation(UP, -0.3 * yaw).to_3x3()
            poser.aim(upper, twist @ rotation((1.0, 0.0, 0.0), -forward).to_3x3() @ hang)
            bend = 14.0 + 22.0 * max(0.0, forward / max(self.plan.swing, 1e-6))
            poser.aim(lower, twist @ rotation((1.0, 0.0, 0.0), -(forward + bend)).to_3x3() @ hang)

    def drop(self):
        worst = 0.0
        for index in range(self.plan.frames):
            phase = index / self.plan.frames
            self.body(phase, 0.0)
            for side in self.sides:
                ankle = self.foot(side, (phase + side["phase"]) % 1.0)[0]
                if self.plan.root_motion:
                    ankle = ankle + FORWARD * self.plan.stride * phase
                hip = self.poser.follow(side["names"]["UpperLeg"]).translation
                worst = max(worst, hip.z - leg_reach_height(hip, ankle, side["upper"], side["lower"], REACH_SLACK))
        return worst

    def frame(self, phase, drop):
        yaw = self.body(phase, drop)
        self.legs(phase)
        self.arms(phase, yaw)


class QuadrupedGait:
    def __init__(self, poser, roles, plan, gait):
        self.poser = poser
        self.roles = roles
        self.plan = plan
        self.gait = gait
        self.legs_info = []
        for key, offset in QUADRUPED_PHASES[gait].items():
            side, end = ("left", key[4:]) if key.startswith("left") else ("right", key[5:])
            names = {part: roles[f"{side}{end}{part}"] for part in ("UpperLeg", "LowerLeg", "Foot")}
            top = poser.rest_head(names["UpperLeg"])
            middle = poser.rest_head(names["LowerLeg"])
            ankle = poser.rest_head(names["Foot"])
            paw = poser.rest_tail(names["Foot"])
            self.legs_info.append({
                "names": names,
                "phase": offset,
                "front": end == "Front",
                "pole": bend_direction(top, middle, ankle),
                "upper": (middle - top).length,
                "lower": (ankle - middle).length,
                "ankle": ankle,
                "paw": paw,
                "carrier": roles["chest"] if end == "Front" else roles["hips"],
            })

    def paw(self, leg, phase):
        along, lift, stance, s = foot_path(phase, self.plan)
        paw = leg["paw"] + FORWARD * along + UP * lift
        fold = 0.0 if stance else (55.0 if leg["front"] else 30.0) * math.sin(math.pi * s) ** 2
        turn = rotation((1.0, 0.0, 0.0), fold)
        ankle = paw - turn.to_3x3() @ (leg["paw"] - leg["ankle"])
        return ankle, turn

    def shift(self):
        root = self.roles.get("root")
        if root is None:
            return Vector()
        return self.poser.pose(root).translation - self.poser.rest[root].translation

    def body(self, phase, drop):
        poser = self.poser
        plan = self.plan
        roles = self.roles
        poser.clear()
        offset = FORWARD * plan.stride * phase if plan.root_motion else Vector()
        if "root" in roles:
            poser.set(roles["root"], Matrix.Translation(offset) @ poser.rest[roles["root"]])
        bob = -plan.bob * (1.0 + math.cos(4.0 * math.pi * phase)) / 2.0
        roll = (3.0 if self.gait == "trot" else 2.0) * math.sin(2.0 * math.pi * phase)
        pitch = 1.5 * math.sin(4.0 * math.pi * phase)
        hips = roles["hips"]
        base = poser.follow(hips)
        turn = rotation((0.0, 1.0, 0.0), roll) @ rotation((1.0, 0.0, 0.0), pitch)
        poser.place(hips, base.translation + Vector((0.0, 0.0, bob - drop)), turn.to_3x3() @ base.to_3x3())
        yaw = 3.0 * math.sin(2.0 * math.pi * phase)
        for role, share in (("spine", 1.0), ("chest", -1.0)):
            if role in roles:
                poser.turn(roles[role], rotation(UP, yaw * share) @ rotation((0.0, 1.0, 0.0), -roll * 0.5))
        if "head" in roles:
            head = roles["head"]
            nod = rotation((1.0, 0.0, 0.0), 3.0 * math.sin(4.0 * math.pi * phase + 0.8))
            poser.place(head, poser.follow(head).translation, nod.to_3x3() @ poser.rest[head].to_3x3())
        for role, lag, amount in (("tail", 0.0, 12.0), ("tailTip", 0.7, 16.0)):
            if role in roles:
                poser.turn(roles[role], rotation(UP, amount * math.sin(2.0 * math.pi * phase - lag)))

    def leg_root(self, leg):
        return self.poser.carried(leg["carrier"], self.poser.rest_head(leg["names"]["UpperLeg"]))

    def legs(self, phase):
        poser = self.poser
        shift = self.shift()
        for leg in self.legs_info:
            names = leg["names"]
            ankle, turn = self.paw(leg, (phase + leg["phase"]) % 1.0)
            ankle = ankle + shift
            top = poser.follow(names["UpperLeg"]).translation
            carrier = leg["carrier"]
            pole = poser.pose(carrier).to_3x3() @ poser.rest[carrier].to_3x3().inverted() @ leg["pole"]
            middle, _ = two_bone(top, ankle, leg["upper"], leg["lower"], pole)
            poser.aim(names["UpperLeg"], middle - top, top)
            poser.aim(names["LowerLeg"], ankle - middle)
            poser.place(names["Foot"], ankle, turn.to_3x3() @ poser.rest[names["Foot"]].to_3x3())

    def drop(self):
        worst = 0.0
        for index in range(self.plan.frames):
            phase = index / self.plan.frames
            self.body(phase, 0.0)
            shift = self.shift()
            for leg in self.legs_info:
                ankle = self.paw(leg, (phase + leg["phase"]) % 1.0)[0] + shift
                top = self.poser.follow(leg["names"]["UpperLeg"]).translation
                worst = max(worst, top.z - leg_reach_height(top, ankle, leg["upper"], leg["lower"], REACH_SLACK))
        return worst

    def frame(self, phase, drop):
        self.body(phase, drop)
        self.legs(phase)


def leg_length(poser, roles, kind):
    if kind == "humanoid":
        top = poser.rest_head(roles["leftUpperLeg"])
        return top.z - poser.rest_tail(roles["leftToes"]).z
    top = poser.rest_head(roles["leftFrontUpperLeg"])
    return top.z - poser.rest_tail(roles["leftFrontFoot"]).z
