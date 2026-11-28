"""Armature helpers: bone name checks, mirrored names, lookup and local coordinates."""

import json
import math
import re

import bpy
from mathutils import Vector

from .errors import bad_args, not_found
from .limits import ELEMENT_NAME_LENGTH, MAX_ARMATURE_BONES, TURN
from .operators import edit_mode
from .schema import boolean, number, obj as object_schema, point3, string
from .util import get_object, rounded, vec

MAX_BONES = MAX_ARMATURE_BONES
MIN_BONE_LENGTH = 1e-4
RIG_PROPERTY = "blendworks_rig"
NAME_PATTERN = re.compile(r"^[^\x00-\x1f]{1,63}$")

SIDE_PREFIXES = (("Left", "Right"), ("left", "right"), ("LEFT", "RIGHT"), ("L_", "R_"), ("l_", "r_"))
SIDE_SUFFIXES = ((".L", ".R"), (".l", ".r"), ("_L", "_R"), ("_l", "_r"), ("-L", "-R"), ("-l", "-r"), (" L", " R"), ("Left", "Right"), ("_left", "_right"))

BONE_FIELDS = {
    "name": string(f"Bone name, at most {ELEMENT_NAME_LENGTH} characters.", max_length=ELEMENT_NAME_LENGTH),
    "head": point3("Head of the bone [x, y, z] in metres, world space."),
    "tail": point3("Tail of the bone [x, y, z] in metres, world space."),
    "roll": number("Roll about the bone's own axis in degrees.", -TURN, TURN, 0.0),
    "parent": string("Parent bone.", max_length=ELEMENT_NAME_LENGTH),
    "connect": boolean("Join the head to the parent's tail, so the bone cannot move away from it.", False),
    "deform": boolean("The bone deforms skinned meshes; false for control bones such as IK targets.", True),
}
BONE_SCHEMA = object_schema(BONE_FIELDS, ["name", "head", "tail"])


def side_of(name):
    for left, right in SIDE_PREFIXES:
        if name.startswith(left) and len(name) > len(left):
            return "left", right + name[len(left):]
        if name.startswith(right) and len(name) > len(right):
            return "right", left + name[len(right):]
    for left, right in SIDE_SUFFIXES:
        if name.endswith(left) and len(name) > len(left):
            return "left", name[: -len(left)] + right
        if name.endswith(right) and len(name) > len(right):
            return "right", name[: -len(right)] + left
    return None, None


def mirrored_name(name):
    return side_of(name)[1]


def get_armature(name):
    obj = get_object(name)
    if obj.type != "ARMATURE":
        raise bad_args(f"{name} is a {obj.type.lower()}, not an armature")
    return obj


def check_bone_name(name):
    if not NAME_PATTERN.match(name):
        raise bad_args(f"bone name {name!r} must be 1 to 63 printable characters")


def require_bone(armature, name):
    bone = armature.data.bones.get(name)
    if bone is None:
        raise not_found(f"{armature.name} has no bone named {name}")
    return bone


def check_length(name, head, tail):
    if (Vector(tail) - Vector(head)).length < MIN_BONE_LENGTH:
        raise bad_args(f"bone {name} needs its tail at least {MIN_BONE_LENGTH} m from its head")


def to_local(armature, point):
    return armature.matrix_world.inverted() @ Vector(point)


def to_world(armature, point):
    return armature.matrix_world @ Vector(point)


def bone_entry(armature, bone):
    head = to_world(armature, bone.head_local)
    tail = to_world(armature, bone.tail_local)
    return {
        "name": bone.name,
        "head": vec(head),
        "tail": vec(tail),
        "roll": rounded(math.degrees(bone_roll(bone)), 4),
        "length": rounded((tail - head).length),
        "parent": bone.parent.name if bone.parent else None,
        "connect": bone.use_connect,
        "deform": bone.use_deform,
    }


def bone_roll(bone):
    return bpy.types.Bone.AxisRollFromMatrix(bone.matrix_local.to_3x3())[1]


def bones_report(armature, names=None):
    chosen = armature.data.bones if names is None else [armature.data.bones[name] for name in names]
    return [bone_entry(armature, bone) for bone in chosen]


def apply_bone(armature, edit_bone, spec):
    if "head" in spec:
        edit_bone.head = to_local(armature, spec["head"])
    if "tail" in spec:
        edit_bone.tail = to_local(armature, spec["tail"])
    if "roll" in spec:
        edit_bone.roll = math.radians(spec["roll"])
    if "deform" in spec:
        edit_bone.use_deform = spec["deform"]


def link_parents(armature, specs):
    bones = armature.data.edit_bones
    for spec in specs:
        if "parent" not in spec and not spec.get("clear_parent"):
            continue
        edit_bone = bones[spec["name"]]
        if spec.get("clear_parent"):
            edit_bone.parent = None
            edit_bone.use_connect = False
            continue
        parent = bones.get(spec["parent"])
        if parent is None:
            raise not_found(f"{armature.name} has no bone named {spec['parent']} to parent {spec['name']} to")
        if parent == edit_bone or is_descendant(parent, edit_bone):
            raise bad_args(f"parenting {spec['name']} to {spec['parent']} would make a loop")
        edit_bone.parent = parent
    for spec in specs:
        if "connect" in spec:
            edit_bone = bones[spec["name"]]
            if spec["connect"] and edit_bone.parent is None:
                raise bad_args(f"bone {edit_bone.name} has no parent to connect to")
            edit_bone.use_connect = spec["connect"]


def is_descendant(bone, ancestor):
    current = bone.parent
    while current is not None:
        if current == ancestor:
            return True
        current = current.parent
    return False


def add_bones(ctx, armature, specs):
    seen = set()
    for spec in specs:
        check_bone_name(spec["name"])
        if spec["name"] in seen or spec["name"] in armature.data.bones:
            raise bad_args(f"{armature.name} already has a bone named {spec['name']}")
        seen.add(spec["name"])
        check_length(spec["name"], spec["head"], spec["tail"])
    if len(armature.data.bones) + len(specs) > MAX_BONES:
        raise bad_args(f"an armature holds at most {MAX_BONES} bones")
    with edit_mode(ctx.view_layer, armature):
        for spec in specs:
            edit_bone = armature.data.edit_bones.new(spec["name"])
            edit_bone.head = to_local(armature, spec["head"])
            edit_bone.tail = to_local(armature, spec["tail"])
            edit_bone.roll = math.radians(spec.get("roll", 0.0))
            edit_bone.use_deform = spec.get("deform", True)
        link_parents(armature, specs)
    return [spec["name"] for spec in specs]


def new_armature(ctx, name, location):
    data = bpy.data.armatures.new(name)
    data.display_type = "OCTAHEDRAL"
    obj = bpy.data.objects.new(name, data)
    ctx.scene.collection.objects.link(obj)
    obj.location = Vector(location)
    obj.show_in_front = True
    ctx.view_layer.update()
    return obj


def rig_metadata(armature):
    raw = armature.data.get(RIG_PROPERTY)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def store_metadata(armature, metadata):
    armature.data[RIG_PROPERTY] = json.dumps(metadata, sort_keys=True)


def rename_roles(armature, renames):
    metadata = rig_metadata(armature)
    roles = metadata.get("roles")
    if not roles or not renames:
        return
    metadata["roles"] = {role: renames.get(bone, bone) for role, bone in roles.items()}
    store_metadata(armature, metadata)


def deforming_armatures(obj):
    found = []
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object is not None and modifier.object.type == "ARMATURE":
            found.append(modifier.object)
    if obj.parent is not None and obj.parent.type == "ARMATURE" and obj.parent_type == "ARMATURE":
        found.append(obj.parent)
    unique = []
    for armature in found:
        if armature not in unique:
            unique.append(armature)
    return unique
