"""Parity checks between the original and the loaded asset (modifiers, particles, curves)."""

import bpy

LEVEL_MODIFIERS = {"SUBSURF", "MULTIRES"}
FULL_PERCENTAGE = 100


def match_modifiers(obj):
    for modifier in obj.modifiers:
        modifier.show_viewport = modifier.show_render
        if modifier.type in LEVEL_MODIFIERS:
            modifier.levels = modifier.render_levels
        if modifier.type == "SCREW":
            modifier.steps = modifier.render_steps


def match_particles(obj):
    for system in getattr(obj, "particle_systems", []):
        settings = system.settings
        if settings is None:
            continue
        settings.display_percentage = FULL_PERCENTAGE
        settings.child_percent = settings.rendered_child_count
        settings.display_step = settings.render_step
        if settings.render_type in {"OBJECT", "COLLECTION"}:
            settings.display_method = "RENDER"


def match_curves():
    for curve in bpy.data.curves:
        if getattr(curve, "render_resolution_u", 0) > 0:
            curve.resolution_u = curve.render_resolution_u
        if getattr(curve, "render_resolution_v", 0) > 0:
            curve.resolution_v = curve.render_resolution_v
    for meta in bpy.data.metaballs:
        meta.resolution = meta.render_resolution


def match_render_settings(scene):
    for obj in scene.objects:
        match_modifiers(obj)
        match_particles(obj)
        obj.show_instancer_for_viewport = obj.show_instancer_for_render
    match_curves()
