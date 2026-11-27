import bpy

assert "shared_probe_handler" not in [getattr(handler, "__name__", "") for handler in bpy.app.handlers.depsgraph_update_post]
assert not hasattr(bpy.types, "SHARED_PROBE_PG_leak")
