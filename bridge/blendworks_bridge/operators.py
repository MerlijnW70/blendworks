"""Contexts for running Blender operators: window, selection and edit mode."""

import contextlib

import bpy


def window_context():
    manager = bpy.context.window_manager
    if manager is None or bpy.app.background:
        return {}
    for window in manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == "VIEW_3D":
                region = next((region for region in area.regions if region.type == "WINDOW"), None)
                if region is not None:
                    return {"window": window, "screen": screen, "area": area, "region": region}
        if bpy.context.window is None:
            return {"window": window, "screen": screen}
    return {}


def operator_context(active, objects=None):
    selected = list(objects) if objects is not None else ([active] if active is not None else [])
    override = window_context()
    override.update(
        {
            "object": active,
            "active_object": active,
            "selected_objects": selected,
            "selected_editable_objects": selected,
        }
    )
    return override


@contextlib.contextmanager
def selection_kept(view_layer):
    active = view_layer.objects.active.name if view_layer.objects.active else None
    selected = {obj.name for obj in view_layer.objects if obj.select_get(view_layer=view_layer)}
    try:
        yield
    finally:
        for obj in view_layer.objects:
            obj.select_set(obj.name in selected, view_layer=view_layer)
        view_layer.objects.active = view_layer.objects.get(active) if active else None


@contextlib.contextmanager
def only_selected(view_layer, active, objects):
    with selection_kept(view_layer):
        for obj in view_layer.objects:
            obj.select_set(False, view_layer=view_layer)
        for obj in objects:
            obj.select_set(True, view_layer=view_layer)
        view_layer.objects.active = active
        yield


@contextlib.contextmanager
def edit_mode(view_layer, obj):
    with only_selected(view_layer, obj, [obj]):
        with bpy.context.temp_override(**operator_context(obj)):
            bpy.ops.object.mode_set(mode="EDIT")
            try:
                yield
            finally:
                bpy.ops.object.mode_set(mode="OBJECT")
