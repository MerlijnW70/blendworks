import math
import os
import struct

from mathutils import Matrix, Quaternion

from judge_common import JudgeError
from judge_gltf import Buffers, entries, whole

FLOAT = 5126
MAT4_BYTES = 64
POSITION_FLOOR = 1e-4
POSITION_RATIO = 1e-5
ANGLE_TOLERANCE = 0.01
SCALE_TOLERANCE = 1e-4
MAX_LISTED = 10
NAME_LENGTH = 120


class BindUnreadable(Exception):
    pass


def numbers(value, count, what):
    if not isinstance(value, list) or len(value) != count:
        raise BindUnreadable(f"{what} does not hold {count} numbers")
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) for item in value):
        raise BindUnreadable(f"{what} holds a value that is not a finite number")
    return [float(item) for item in value]


def column_major(values):
    return Matrix([[values[column * 4 + row] for column in range(4)] for row in range(4)])


def node_local(node, index):
    if not isinstance(node, dict):
        raise BindUnreadable(f"node {index} is not an object")
    if "matrix" in node:
        return column_major(numbers(node["matrix"], 16, f"the matrix of node {index}"))
    translation = numbers(node.get("translation", [0.0, 0.0, 0.0]), 3, f"the translation of node {index}")
    x, y, z, w = numbers(node.get("rotation", [0.0, 0.0, 0.0, 1.0]), 4, f"the rotation of node {index}")
    scale = numbers(node.get("scale", [1.0, 1.0, 1.0]), 3, f"the scale of node {index}")
    rotation = Quaternion((w, x, y, z))
    if rotation.magnitude == 0:
        raise BindUnreadable(f"the rotation of node {index} is zero")
    return Matrix.Translation(translation) @ rotation.normalized().to_matrix().to_4x4() @ Matrix.Diagonal((*scale, 1.0))


def world_matrices(nodes):
    parents = {}
    for index, node in enumerate(nodes):
        for child in (node.get("children") or []) if isinstance(node, dict) else []:
            if whole(child) and child < len(nodes):
                parents.setdefault(child, index)
    worlds = {}

    def world(index):
        chain = []
        current = index
        while current is not None and current not in worlds:
            if current in chain:
                raise BindUnreadable(f"the node hierarchy has a cycle through node {current}")
            chain.append(current)
            current = parents.get(current)
        matrix = Matrix.Identity(4) if current is None else worlds[current]
        for link in reversed(chain):
            matrix = matrix @ node_local(nodes[link], link)
            worlds[link] = matrix
        return worlds[index]

    return world


def entry(items, index, what):
    if not whole(index) or index >= len(items) or not isinstance(items[index], dict):
        raise BindUnreadable(f"{what} {index} is missing")
    return items[index]


def inverse_binds(document, buffers, skin, joints):
    index = skin.get("inverseBindMatrices")
    if index is None:
        return [Matrix.Identity(4) for _ in range(joints)]
    accessor = entry(entries(document, "accessors"), index, "the inverse bind matrix accessor")
    if accessor.get("componentType") != FLOAT or accessor.get("type") != "MAT4" or "sparse" in accessor:
        raise BindUnreadable("the inverse bind matrices are not a plain float MAT4 accessor")
    if not whole(accessor.get("count")) or accessor["count"] < joints:
        raise BindUnreadable("the skin has fewer inverse bind matrices than joints")
    view = entry(entries(document, "bufferViews"), accessor.get("bufferView"), "the inverse bind matrix bufferView")
    stride = view.get("byteStride", MAT4_BYTES)
    start = view.get("byteOffset", 0)
    offset = accessor.get("byteOffset", 0)
    if not all(whole(value) for value in (stride, start, offset, view.get("byteLength"))) or stride < MAT4_BYTES:
        raise BindUnreadable("the inverse bind matrix bufferView is malformed")
    length = (joints - 1) * stride + MAT4_BYTES if joints > 0 else 0
    if offset + length > view["byteLength"]:
        raise BindUnreadable("the inverse bind matrices run past their bufferView")
    try:
        data = buffers.read(view.get("buffer"), start + offset, length)
    except (JudgeError, OSError):
        raise BindUnreadable("the buffer of the inverse bind matrices cannot be read") from None
    if len(data) < length:
        raise BindUnreadable("the buffer of the inverse bind matrices is truncated")
    matrices = []
    for joint in range(joints):
        values = struct.unpack_from("<16f", data, joint * stride)
        if not all(math.isfinite(value) for value in values):
            raise BindUnreadable("an inverse bind matrix holds a value that is not finite")
        matrices.append(column_major(values))
    return matrices


def joint_difference(posed, rest):
    posed_location, posed_rotation, posed_scale = posed.decompose()
    rest_location, rest_rotation, rest_scale = rest.decompose()
    angle = posed_rotation.rotation_difference(rest_rotation).angle
    angle = min(angle, 2 * math.pi - angle)
    scale = max(abs(posed_scale[axis] / rest_scale[axis] - 1.0) if rest_scale[axis] != 0 else math.inf for axis in range(3))
    return (posed_location - rest_location).length, math.degrees(angle), scale


def gltf_differences(path, document, binary):
    buffers = Buffers(document, os.path.dirname(os.path.abspath(path)), binary)
    nodes = entries(document, "nodes")
    skins = entries(document, "skins")
    world = world_matrices(nodes)
    worst = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or "skin" not in node or "mesh" not in node:
            continue
        skin = entry(skins, node["skin"], "skin")
        joints = skin.get("joints")
        if not isinstance(joints, list) or not joints or not all(whole(joint) and joint < len(nodes) for joint in joints):
            raise BindUnreadable(f"skin {node['skin']} has malformed joints")
        mesh_world = world(index)
        for joint, inverse_bind in zip(joints, inverse_binds(document, buffers, skin, len(joints))):
            try:
                bind_world = mesh_world @ inverse_bind.inverted()
            except ValueError:
                raise BindUnreadable(f"the inverse bind matrix of node {joint} cannot be inverted") from None
            joint_world = world(joint)
            name = nodes[joint].get("name")
            name = name if isinstance(name, str) else f"node {joint}"
            difference = joint_difference(joint_world, bind_world)
            previous = worst.get(joint)
            worst[joint] = (name[:NAME_LENGTH], *(difference if previous is None else map(max, previous[1:], difference)))
    return list(worst.values())


def blender_differences(rigs, depsgraph):
    differences = []
    for rig in sorted(rigs, key=lambda obj: obj.name):
        evaluated = rig.evaluated_get(depsgraph)
        world = evaluated.matrix_world
        for bone in rig.data.bones:
            if bone.use_deform:
                pose = evaluated.pose.bones[bone.name].matrix
                differences.append((bone.name[:NAME_LENGTH], *joint_difference(world @ pose, world @ bone.matrix_local)))
    return differences


def finite(value):
    return value if math.isfinite(value) else 1e9


def rest_pose_result(method, differences, extent, reason=None):
    position = max(POSITION_FLOOR, POSITION_RATIO * extent)
    tolerance = {"position": round(position, 6), "angle": ANGLE_TOLERANCE, "scale": SCALE_TOLERANCE}
    if reason is not None:
        return {"method": method, "bound": None, "joints": 0, "jointsOff": 0, "maxOffset": 0.0, "maxAngle": 0.0, "maxScaleError": 0.0, "offJoints": [], "tolerance": tolerance, "reason": reason[:300]}
    off = sorted({name for name, offset, angle, scale in differences if offset > position or angle > ANGLE_TOLERANCE or scale > SCALE_TOLERANCE})
    return {
        "method": method,
        "bound": not off,
        "joints": len(differences),
        "jointsOff": len(off),
        "maxOffset": round(finite(max((item[1] for item in differences), default=0.0)), 6),
        "maxAngle": round(finite(max((item[2] for item in differences), default=0.0)), 4),
        "maxScaleError": round(finite(max((item[3] for item in differences), default=0.0)), 6),
        "offJoints": off[:MAX_LISTED],
        "tolerance": tolerance,
        "reason": None,
    }
