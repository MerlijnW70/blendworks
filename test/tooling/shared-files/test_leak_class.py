import bpy


class SHARED_PROBE_PG_leak(bpy.types.PropertyGroup):
    value: bpy.props.IntProperty()


bpy.utils.register_class(SHARED_PROBE_PG_leak)
