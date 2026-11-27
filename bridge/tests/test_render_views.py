import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from fingerprint import differences, fingerprint
from harness import run
from view_helpers import QUICK, line_coverage, line_profile, look_down, quad_grid, render, saturation, white_world

from blendworks_bridge import render_outputs, view_materials, wire_edges

LINE_TOLERANCE = 0.25
EMPTY = 0.1
WIDTH = view_materials.DEFAULT_WIRE_WIDTH


def coloured_scene(bridge):
    for name, colour, x in (("Red", [0.9, 0.05, 0.05], -1.2), ("Green", [0.05, 0.8, 0.1], 0.0), ("Blue", [0.05, 0.1, 0.9], 1.2)):
        bridge.ok("add_primitive", type="cube", name=name, size=0.8, location=[x, 4.0, 0.0])
        bridge.ok("add_material", name=name, base_color=colour, roughness=0.5)
        bridge.ok("assign_material", name=name, material=name)
    bridge.ok("add_primitive", type="plane", name="Floor", size=12.0, location=[0.0, 4.0, -0.4])
    bridge.ok("add_material", name="Yellow", base_color=[0.9, 0.8, 0.1], roughness=0.8)
    bridge.ok("assign_material", name="Floor", material="Yellow")
    bridge.ok("add_light", type="sun", name="Sun", rotation=[50.0, 0.0, 20.0], energy=3.0)
    bridge.ok("add_camera", name="Cam", location=[0.0, -1.0, 2.0], rotation=[70.0, 0.0, 0.0])
    white_world(bridge, 0.6)


def volume_material(name, kind, surface=None):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    volume = tree.nodes.new(kind)
    tree.links.new(volume.outputs[0], output.inputs["Volume"])
    if surface is not None:
        shader = tree.nodes.new(surface)
        shader.inputs["Color"].default_value = (0.1, 0.3, 1.0, 1.0)
        tree.links.new(shader.outputs[0], output.inputs["Surface"])
    return material


def add_fog(bridge):
    bridge.ok("add_primitive", type="cube", name="FogBox", size=30.0, location=[0.0, 4.0, 0.0])
    bpy.data.objects["FogBox"].data.materials.append(volume_material("Fog", "ShaderNodeVolumeAbsorption"))


def test_clay_has_no_colour_where_shaded_has_plenty(bridge):
    coloured_scene(bridge)
    shaded, _ = render(bridge, "shaded")
    clay, result = render(bridge, "clay", shading="clay")
    assert result["shading"] == "clay"
    assert float(saturation(shaded).mean()) > 0.4
    assert float(saturation(clay).max()) < 0.02
    assert float(np.abs(clay - shaded).mean()) > 0.05
    assert clay.max(axis=-1).std() > 0.02


def scene_state():
    scene = bpy.context.scene
    view = scene.view_settings
    return (
        len(scene.objects),
        sorted(material.name for material in bpy.data.materials),
        {obj.name: ([modifier.name for modifier in obj.modifiers], obj.modifiers.active.name if obj.modifiers.active else None, obj.hide_render) for obj in scene.objects},
        sorted(group.name for group in bpy.data.node_groups),
        bpy.context.view_layer.material_override,
        (view.view_transform, view.look, view.exposure, view.gamma),
    )


def failing(owner, name):
    original = getattr(owner, name)

    def explode(*arguments, **keywords):
        raise RuntimeError("forced failure")

    setattr(owner, name, explode)
    return lambda: setattr(owner, name, original)


def test_every_view_and_a_forced_failure_leave_the_scene_as_it_was(bridge):
    coloured_scene(bridge)
    add_fog(bridge)
    bpy.data.objects["Red"].modifiers.new("Smooth", "SUBSURF")
    bridge.ok("add_primitive", type="cube", name="Bare", size=0.4, location=[0.0, 2.5, 0.0])
    bridge.ok("curve_from_points", name="Wire", points=[[-1.0, 3.0, 0.5], [0.0, 3.2, 0.8], [1.0, 3.0, 0.5]], bevel_depth=0.03)
    twin = bpy.data.objects["Green"].copy()
    twin.location.z += 1.0
    bpy.context.scene.collection.objects.link(twin)
    bpy.context.view_layer.update()
    before, state = fingerprint(), scene_state()
    for shading in ("shaded", "clay", "wireframe", "normals"):
        _, result = render(bridge, f"keep_{shading}", shading=shading)
        assert result["shading"] == shading
        if shading == "wireframe":
            assert result["wire_polygon_objects"] >= 2
        assert fingerprint() == before, differences(before, fingerprint())
        assert scene_state() == state
    for owner, name in ((render_outputs, "render_layers"), (view_materials, "wire_group")):
        restore = failing(owner, name)
        try:
            reply = bridge.call("render_final", path="failed.exr", shading="wireframe", **QUICK)
        finally:
            restore()
        assert not reply["ok"] and "forced failure" in reply["error"]["message"]
        assert fingerprint() == before, (name, differences(before, fingerprint()))
        assert scene_state() == state
    assert not any(obj.modifiers.get(wire_edges.MODIFIER) for obj in bpy.context.scene.objects)

    original = wire_edges.PolygonEdges.remove_group

    def stuck(edges):
        raise RuntimeError("stuck restore step")

    wire_edges.PolygonEdges.remove_group = stuck
    try:
        reply = bridge.call("render_final", path="stuck.exr", shading="wireframe", **QUICK)
    finally:
        wire_edges.PolygonEdges.remove_group = original
    assert not reply["ok"] and "stuck restore step" in reply["error"]["message"]
    bpy.data.node_groups.remove(bpy.data.node_groups[wire_edges.GROUP_NAME])
    assert fingerprint() == before, differences(before, fingerprint())
    assert scene_state() == state


def test_clay_greys_liquids_hair_and_instances(bridge):
    coloured_scene(bridge)
    plain, _ = render(bridge, "plain", shading="clay")

    bridge.ok("add_primitive", type="cube", name="Water", size=0.9, location=[0.0, 3.0, 0.5])
    bpy.data.objects["Water"].data.materials.append(volume_material("Water", "ShaderNodeVolumeAbsorption", "ShaderNodeBsdfGlass"))
    bridge.ok("add_primitive", type="plane", name="Turf", size=1.5, location=[-0.3, 2.5, -0.35])
    turf = bpy.data.objects["Turf"]
    turf.data.materials.append(bpy.data.materials["Yellow"])
    grass = bpy.data.materials.new("Grass")
    grass.use_nodes = True
    grass.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.1, 1.0)
    turf.data.materials.append(grass)
    settings = turf.modifiers.new("Hair", "PARTICLE_SYSTEM").particle_system.settings
    settings.type = "HAIR"
    settings.count = 300
    settings.hair_length = 0.4
    settings.material = 2
    bridge.ok("add_primitive", type="cube", name="Source", size=0.3, location=[0.0, 0.0, 0.0])
    bridge.ok("assign_material", name="Source", material="Red")
    group = bpy.data.collections.new("Element")
    group.objects.link(bpy.data.objects["Source"])
    bpy.context.scene.collection.objects.unlink(bpy.data.objects["Source"])
    holder = bpy.data.objects.new("Holder", None)
    holder.instance_type = "COLLECTION"
    holder.instance_collection = group
    holder.location = (0.0, 4.2, 0.1)
    bpy.context.scene.collection.objects.link(holder)

    shaded, _ = render(bridge, "shaded_all")
    clay, _ = render(bridge, "clay_all", shading="clay")
    assert float(saturation(shaded).max()) > 0.5
    assert float(saturation(clay).max()) < 0.02
    assert float(np.abs(clay - plain).mean()) > 1e-3
    turf.modifiers.remove(turf.modifiers["Hair"])
    bare, _ = render(bridge, "bare", shading="clay")
    assert float(np.abs(clay - bare).mean()) > 1e-4


def test_clay_renders_a_filled_cup_of_every_liquid_as_a_grey_surface(bridge):
    coloured_scene(bridge)
    bridge.ok("lathe", name="Cup", profile=[[0.0, 0.0], [0.42, 0.0], [0.42, 0.8], [0.4, 0.8], [0.4, 0.02], [0.0, 0.02]], segments=48)
    bridge.ok("transform", name="Cup", location=[0.0, 2.0, -0.4])
    for preset in ("water_fresh", "wine", "milk", "molten_metal"):
        bridge.ok("liquid_fill", container="Cup", preset=preset, level=0.3, name="Liquid")
        shaded, _ = render(bridge, "liquid_shaded")
        clay, _ = render(bridge, "liquid_clay", shading="clay")
        assert float(saturation(clay).max()) < 0.02, preset
        assert float(np.abs(clay - shaded).mean()) > 1e-3, preset
        bridge.ok("delete", names=["Liquid"])


def test_wireframe_lines_sit_on_a_known_grid_at_a_constant_pixel_width(bridge):
    cells, size, resolution = 8, 2.0, 240
    white_world(bridge)
    grid = quad_grid("Grid", cells, size / 2.0)
    grid.scale = (2.0, 2.0, 1.0)
    look_down("Top", 5.0, resolution, ortho_scale=2.4)
    options = dict(width=resolution, height=resolution, samples=64)
    coverage, result = line_coverage(bridge, "grid", **options)
    assert result["wire_edges_drawn"] == "polygon" and result["wire_width"] == WIDTH
    per_metre = resolution / 2.4
    spacing = size / cells * per_metre
    edge = resolution / 2 - size / 2 * per_metre
    row = int(edge + 3.5 * spacing)
    for number in range(1, cells):
        expected = edge + number * spacing
        width, centre = line_profile(coverage, row, expected, 5)
        assert abs(centre - expected) < LINE_TOLERANCE, (number, centre, expected)
        assert abs(width - WIDTH) < LINE_TOLERANCE, (number, width)
    for cell in range(cells):
        x, y = int(edge + (cell + 0.5) * spacing), int(edge + (cell + 0.5) * spacing)
        for step in (-2, 0, 2):
            assert coverage[y + step, x + step] < EMPTY, (cell, step)
    triangles, drawn = line_coverage(bridge, "grid_triangles", wire_triangles=True, **options)
    assert drawn["wire_edges_drawn"] == "triangle"
    x = y = int(edge + 3.5 * spacing)
    assert triangles[y, x] > 0.5


def test_wireframe_width_is_the_same_at_two_distances(bridge):
    cells, size, resolution = 8, 2.0, 360
    white_world(bridge)
    quad_grid("Grid", cells, size)
    camera = look_down("Top", 4.0, resolution)
    widths = []
    for height in (4.0, 8.0):
        camera.location = (0.0, 0.0, height)
        coverage, _ = line_coverage(bridge, f"distance_{int(height)}", width=resolution, height=resolution, samples=64)
        spacing = size / cells * resolution * 50.0 / 36.0 / height
        row = resolution // 2 + int(spacing / 2)
        width, centre = line_profile(coverage, row, resolution / 2, 5)
        assert abs(centre - resolution / 2) < LINE_TOLERANCE
        widths.append(width)
    assert all(abs(width - WIDTH) < LINE_TOLERANCE for width in widths), widths
    assert abs(widths[0] - widths[1]) < LINE_TOLERANCE


def tilted_grid_widths(bridge, angle):
    """Widths in pixels of a line along the slope and a line across it, on a grid seen `angle` degrees from its normal."""
    cells, size, resolution, scale = 4, 2.0, 400, 2.4
    grid = quad_grid("Grid", cells, size)
    grid.rotation_euler = (math.radians(90.0 - angle), 0.0, 0.0)
    camera = look_down("Side", 10.0, resolution, ortho_scale=scale)
    camera.location = (0.0, -10.0, 0.0)
    camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    coverage, result = line_coverage(bridge, f"tilt_{int(angle)}", camera="Side", width=resolution, height=resolution, samples=64)
    assert result["wire_edges_drawn"] == "polygon"
    across_cell = size / cells * resolution / scale
    down_cell = across_cell * math.cos(math.radians(angle))
    middle = resolution // 2
    column, row = middle + int(across_cell / 2), middle + int(down_cell / 2)
    along, along_centre = line_profile(coverage, row, middle, 5)
    across, across_centre = line_profile(coverage.T, column, middle, 4)
    bpy.data.objects.remove(grid)
    bpy.data.objects.remove(camera)
    return along, across, along_centre - middle, across_centre - middle


def test_wireframe_width_holds_for_both_line_directions_on_oblique_surfaces(bridge):
    white_world(bridge)
    for angle in (60.0, 70.0, 80.0):
        along, across, along_offset, across_offset = tilted_grid_widths(bridge, angle)
        assert abs(along - WIDTH) < LINE_TOLERANCE and abs(across - WIDTH) < LINE_TOLERANCE, (angle, along, across)
        assert abs(along_offset) < LINE_TOLERANCE and abs(across_offset) < LINE_TOLERANCE, (angle, along_offset, across_offset)


def test_wireframe_width_holds_off_centre_on_ground_seen_in_perspective(bridge):
    """Lines across a ground grid seen 60 degrees from its normal, above and below the middle of the frame, where the
    perspective bends each receding edge away from the view axis."""
    cells, size, resolution = 8, 4.0, 400
    white_world(bridge)
    quad_grid("Ground", cells, size)
    camera = look_down("Eye", 6.0, resolution)
    tilt = math.radians(60.0)
    camera.location = (0.0, -6.0 * math.sin(tilt), 6.0 * math.cos(tilt))
    camera.rotation_euler = (tilt, 0.0, 0.0)
    bpy.context.view_layer.update()
    coverage, _ = line_coverage(bridge, "ground", camera="Eye", width=resolution, height=resolution, samples=64)
    scene = bpy.context.scene

    def screen(x, y):
        point = world_to_camera_view(scene, camera, Vector((x, y, 0.0)))
        return point.x * resolution, (1.0 - point.y) * resolution

    step = size / cells
    measured = []
    for line in range(1, cells):
        y = -size / 2 + line * step
        left, row = screen(0.0, y)
        right, _ = screen(step, y)
        if not 40 < row < resolution - 40 or abs(row - resolution / 2) < 40:
            continue
        width, centre = line_profile(coverage.T, int((left + right) / 2), row, 5)
        measured.append((round(row), width))
        assert abs(width - WIDTH) < LINE_TOLERANCE and abs(centre - row) < LINE_TOLERANCE, (row, width, centre)
    assert len(measured) >= 2 and min(row for row, _ in measured) < resolution / 2 < max(row for row, _ in measured), measured


run(globals())
