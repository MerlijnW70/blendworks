from array import array

from judge_bind import BindUnreadable, blender_differences, gltf_differences, rest_pose_result
from judge_common import JudgeError
from judge_load import gltf_document

MAX_ITEMS = 64
NAME_LENGTH = 120
DEFAULT_WEIGHT_TOLERANCE = 0.01


def skinning_rigs(obj):
    rigs = []
    uses_groups = False
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.show_viewport and modifier.object is not None and modifier.object.type == "ARMATURE":
            rigs.append(modifier.object)
            uses_groups = uses_groups or modifier.use_vertex_groups
    if obj.parent is not None and obj.parent_type == "ARMATURE" and obj.parent.type == "ARMATURE":
        rigs.append(obj.parent)
        uses_groups = True
    return sorted(set(rigs), key=lambda rig: rig.name), uses_groups


def face_vertices(mesh):
    loops = array("i", [0]) * len(mesh.loops)
    mesh.loops.foreach_get("vertex_index", loops)
    return set(loops)


def vertex_weights(obj, deform_names, tolerance):
    mesh = obj.data
    deforming = {group.index for group in obj.vertex_groups if group.name in deform_names}
    on_faces = face_vertices(mesh)
    most = unweighted = not_normalized = 0
    for vertex in mesh.vertices:
        if vertex.index not in on_faces:
            continue
        total = 0.0
        count = 0
        for element in vertex.groups:
            if element.group in deforming and element.weight > 0.0:
                count += 1
                total += element.weight
        most = max(most, count)
        if count == 0:
            unweighted += 1
        elif abs(total - 1.0) > tolerance:
            not_normalized += 1
    return {"vertices": len(on_faces), "maxInfluences": most, "unweighted": unweighted, "notNormalized": not_normalized}


def by_construction(rigs):
    return [(bone.name[:NAME_LENGTH], 0.0, 0.0, 0.0) for rig in sorted(rigs, key=lambda obj: obj.name) for bone in rig.data.bones if bone.use_deform]


def rest_pose(asset, file_format, rigs, extent, depsgraph):
    if file_format == "blend":
        return rest_pose_result("blend", by_construction(rigs), extent)
    if file_format not in ("glb", "gltf"):
        return rest_pose_result(file_format, blender_differences(rigs, depsgraph), extent)
    try:
        document, binary = gltf_document(asset, file_format)
        return rest_pose_result("gltf", gltf_differences(asset, document, binary), extent)
    except (BindUnreadable, JudgeError) as error:
        return rest_pose_result("gltf", [], extent, reason=str(error))


def measure_skin(scene, asset, file_format, tolerance, extent, depsgraph):
    items = []
    rigs_used = set()
    for obj in sorted((candidate for candidate in scene.objects if candidate.type == "MESH" and candidate.data is not None), key=lambda candidate: candidate.name):
        rigs, uses_groups = skinning_rigs(obj)
        if not rigs:
            continue
        deform_names = {bone.name for rig in rigs for bone in rig.data.bones if bone.use_deform} if uses_groups else set()
        item = {"object": obj.name[:NAME_LENGTH], "armatures": [rig.name[:NAME_LENGTH] for rig in rigs][:MAX_ITEMS]}
        item.update(vertex_weights(obj, deform_names, tolerance))
        items.append(item)
        rigs_used.update(rigs)
    return {
        "meshes": len(items),
        "vertices": sum(item["vertices"] for item in items),
        "maxInfluences": max((item["maxInfluences"] for item in items), default=0),
        "unweighted": sum(item["unweighted"] for item in items),
        "notNormalized": sum(item["notNormalized"] for item in items),
        "tolerance": tolerance,
        "restPose": rest_pose(asset, file_format, rigs_used, extent, depsgraph) if items else None,
        "items": items[:MAX_ITEMS],
    }
