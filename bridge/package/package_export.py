"""Exports a LOD package as glb with its ancestors."""

import bpy


def with_ancestors(objects):
    chosen = []
    seen = set()
    for obj in objects:
        node = obj
        while node is not None and node not in seen:
            seen.add(node)
            chosen.append(node)
            node = node.parent
    return chosen


def export_glb(path, objects):
    chosen = with_ancestors(objects)
    layer = bpy.context.view_layer
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    for obj in chosen:
        obj.select_set(True)
    layer.objects.active = chosen[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_animations=False,
    )
