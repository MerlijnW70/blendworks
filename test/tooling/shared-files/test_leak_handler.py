import bpy
from bpy.app.handlers import persistent


@persistent
def shared_probe_handler(*_):
    return None


bpy.app.handlers.depsgraph_update_post.append(shared_probe_handler)
