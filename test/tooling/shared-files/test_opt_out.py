import bpy
from bpy.app.handlers import persistent

BLENDWORKS_FRESH_PROCESS = "leaves a persistent handler behind on purpose"


@persistent
def opted_out_handler(*_):
    return None


bpy.app.handlers.load_post.append(opted_out_handler)
