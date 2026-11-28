"""Measures armatures: bone depths and rig data."""

MAX_ITEMS = 64
MAX_BONE_NAMES = 2048
NAME_LENGTH = 120


def armatures_in(scene):
    return sorted((obj for obj in scene.objects if obj.type == "ARMATURE" and obj.data is not None), key=lambda obj: obj.name)


def bone_depths(bones):
    depths = {}
    for bone in bones:
        chain = []
        current = bone
        while current is not None and current.name not in depths:
            chain.append(current)
            current = current.parent
        depth = 0 if current is None else depths[current.name]
        for link in reversed(chain):
            depth += 1
            depths[link.name] = depth
    return depths


def measure_armature(obj):
    bones = list(obj.data.bones)
    depths = bone_depths(bones)
    roots = sorted(bone.name[:NAME_LENGTH] for bone in bones if bone.parent is None)
    return {
        "name": obj.name[:NAME_LENGTH],
        "bones": len(bones),
        "deformBones": sum(1 for bone in bones if bone.use_deform),
        "depth": max(depths.values(), default=0),
        "roots": roots[:MAX_ITEMS],
    }, [bone.name[:NAME_LENGTH] for bone in bones]


def measure_rig(scene):
    items = []
    names = []
    roots = []
    for obj in armatures_in(scene):
        item, bone_names = measure_armature(obj)
        items.append(item)
        names.extend(bone_names)
        roots.extend(item["roots"])
    return {
        "armatures": len(items),
        "bones": sum(item["bones"] for item in items),
        "deformBones": sum(item["deformBones"] for item in items),
        "depth": max((item["depth"] for item in items), default=0),
        "roots": sorted(roots)[:MAX_ITEMS],
        "boneNames": sorted(names)[:MAX_BONE_NAMES],
        "items": items[:MAX_ITEMS],
    }
