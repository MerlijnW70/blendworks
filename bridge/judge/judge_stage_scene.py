from contextlib import contextmanager

import bpy

CREATED_DATA = ("objects", "cameras", "lights", "materials", "worlds", "node_groups", "meshes", "images")
KEPT_IMAGE_TYPES = {"RENDER_RESULT", "COMPOSITING"}


def data_pointers():
    return {kind: {block.as_pointer() for block in getattr(bpy.data, kind)} for kind in CREATED_DATA}


def remove_created(before):
    for kind in CREATED_DATA:
        collection = getattr(bpy.data, kind)
        for block in list(collection):
            if block.as_pointer() in before[kind]:
                continue
            if kind == "images" and block.type in KEPT_IMAGE_TYPES:
                continue
            collection.remove(block)


@contextmanager
def stage_scene(source, name):
    before = data_pointers()
    scene = source.copy()
    scene.name = name
    try:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            yield scene
    finally:
        bpy.data.scenes.remove(scene)
        remove_created(before)
