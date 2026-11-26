import bpy

FLAG = "blendworks_weather"
KINDS = ("sun", "cloud_volume", "cloud_shadow", "rain_veil", "rain_streaks", "lightning", "flash")
COLLECTION = "Weather"


def tag(obj, kind):
    if kind not in KINDS:
        raise ValueError(f"unknown weather object kind {kind}")
    obj[FLAG] = kind
    return obj


def kind_of(obj):
    value = obj.get(FLAG)
    return value if isinstance(value, str) else None


def objects(scene, kinds=None):
    return [obj for obj in scene.objects if kind_of(obj) is not None and (kinds is None or kind_of(obj) in kinds)]


def collection(scene):
    found = bpy.data.collections.get(COLLECTION)
    if found is None:
        found = bpy.data.collections.new(COLLECTION)
    if found.name not in scene.collection.children:
        scene.collection.children.link(found)
    return found


def link(scene, obj, kind, hidden=True):
    """Link a weather object into the Weather collection; hidden ones stay out of the viewport, framing and export."""
    collection(scene).objects.link(obj)
    tag(obj, kind)
    if hidden:
        layer = bpy.context.view_layer
        layer.update()
        if layer.objects.get(obj.name) is not None:
            obj.hide_set(True, view_layer=layer)
        obj.hide_select = True
    return obj


def remove_data(data):
    if data is None or data.users > 0:
        return
    materials = list(getattr(data, "materials", []))
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Light):
        bpy.data.lights.remove(data)
    elif isinstance(data, bpy.types.Curve):
        bpy.data.curves.remove(data)
    for material in materials:
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)


def remove(scene, kinds=None):
    gone = []
    for obj in objects(scene, kinds):
        data = obj.data
        gone.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)
        remove_data(data)
    found = bpy.data.collections.get(COLLECTION)
    if found is not None and len(found.all_objects) == 0:
        bpy.data.collections.remove(found)
    return sorted(gone)


def remove_all(scene):
    return remove(scene)
