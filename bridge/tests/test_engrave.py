import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from kit_helpers import is_closed_manifold, volume

from blendworks_bridge.glyph_data import GLYPHS
from blendworks_bridge.glyphs import CAP_HEIGHT, CHARACTERS, PLANETS, SYMBOL_SCALE, ZODIAC
from blendworks_bridge.outlines import signed_area

DEGENERATE_AREA = 1e-12
RADIUS, INNER, HEIGHT = 0.1, 0.09, 0.02
SEGMENTS = 256
SIZE = 0.006
DEPTH = 0.0008


def degenerate_triangles(name):
    mesh = bpy.data.objects[name].data
    mesh.calc_loop_triangles()
    count = 0
    for triangle in mesh.loop_triangles:
        a, b, c = (mesh.vertices[index].co for index in triangle.vertices)
        if (b - a).cross(c - a).length / 2.0 <= DEGENERATE_AREA:
            count += 1
    return count


def font_area(text, size, font=None):
    curve = bpy.data.curves.new("reference", "FONT")
    curve.body = text
    curve.size = size
    if font is not None:
        curve.font = font
    holder = bpy.data.objects.new("reference", curve)
    bpy.context.scene.collection.objects.link(holder)
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = holder.evaluated_get(graph)
    mesh = evaluated.to_mesh()
    total = sum(polygon.area for polygon in mesh.polygons)
    evaluated.to_mesh_clear()
    bpy.data.objects.remove(holder)
    bpy.data.curves.remove(curve)
    return total


def glyph_area(name, size):
    scale = size * SYMBOL_SCALE / 1000.0
    loops = [[(loop[i] * scale, loop[i + 1] * scale) for i in range(0, len(loop), 2)] for loop in GLYPHS[name][1]]
    return sum(abs(signed_area(loop)) * (1 if signed_area(loop) > 0 else -1) for loop in loops)


def ring(bridge, name="Ring"):
    bridge.ok("lathe", name=name, profile=[[INNER, 0], [RADIUS, 0], [RADIUS, HEIGHT], [INNER, HEIGHT]], segments=SEGMENTS, closed=True, shading="flat")


def plate(bridge, name="Plate", size=(0.2, 0.2, 0.02)):
    bridge.ok("add_primitive", type="cube", name=name, size=1.0)
    bridge.ok("transform", name=name, scale=list(size))
    bridge.ok("apply_transform", name=name, scale=True)


def band(**extra):
    return {"cylinder": {"radius": RADIUS, "axis": [0, 0, 1], "centre": [0, 0, 0], **extra}}


def test_engraving_ten_on_a_ring_removes_the_expected_volume(bridge):
    ring(bridge)
    before = volume("Ring")
    result = bridge.ok("engrave", name="Ring", text="10", **band(), size=SIZE, depth=DEPTH, shift=HEIGHT / 2, tolerance=0.00005)
    glyphs = font_area("10", SIZE)
    expected = glyphs * (DEPTH - DEPTH ** 2 / (2 * RADIUS))
    removed = before - volume("Ring")
    assert abs(removed / expected - 1.0) < 0.03, (removed, expected)
    close(-result["volume_change"], removed, 1e-9)
    assert result["manifold"] is True and is_closed_manifold("Ring")
    assert degenerate_triangles("Ring") == 0
    assert result["mode"] == "cut" and result["instances"] == 1 and result["cleaned"]["degenerate_triangles_after"] == 0


def test_embossing_adds_the_expected_volume(bridge):
    ring(bridge)
    before = volume("Ring")
    height = 0.0006
    result = bridge.ok("engrave", name="Ring", text="10", **band(), size=SIZE, height=height, shift=HEIGHT / 2, tolerance=0.00005)
    expected = font_area("10", SIZE) * (height + height ** 2 / (2 * RADIUS))
    added = volume("Ring") - before
    assert abs(added / expected - 1.0) < 0.03, (added, expected)
    assert result["mode"] == "emboss" and result["manifold"] is True and degenerate_triangles("Ring") == 0


def test_the_inside_of_a_ring_reads_from_the_axis(bridge):
    ring(bridge)
    before = volume("Ring")
    bridge.ok("engrave", name="Ring", text="10", **band(side="inner", radius=INNER), size=SIZE, depth=DEPTH, shift=HEIGHT / 2, tolerance=0.00005)
    expected = font_area("10", SIZE) * (DEPTH + DEPTH ** 2 / (2 * INNER))
    assert abs((before - volume("Ring")) / expected - 1.0) < 0.03
    assert is_closed_manifold("Ring") and degenerate_triangles("Ring") == 0


def test_a_flat_surface_loses_exactly_the_glyph_area_times_the_depth(bridge):
    plate(bridge)
    before = volume("Plate")
    result = bridge.ok("engrave", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 1]}, size=0.03, depth=0.002)
    expected = font_area("10", 0.03) * 0.002
    assert abs((before - volume("Plate")) / expected - 1.0) < 0.01
    assert result["surface"] == "plane" and is_closed_manifold("Plate") and degenerate_triangles("Plate") == 0


def test_a_face_region_is_found_anchored_at_its_centre_and_checked_for_fit(bridge):
    plate(bridge)
    fits = bridge.ok("engrave", name="Plate", text="10", faces={"facing": "up"}, size=0.03, depth=0.002)
    assert fits["fits"] is True and fits["surface"] == "faces"
    bridge.ok("engrave", name="Plate", text="10", faces={"facing": "up"}, size=0.03, depth=0.001, offset=0.09)
    plate(bridge, "Other", (0.015, 0.015, 0.02))
    too_big = bridge.ok("engrave", name="Other", text="10", faces={"facing": "up"}, size=0.03, depth=0.001)
    assert too_big["fits"] is False
    bridge.refuse("engrave", "bad_args", name="Plate", text="10", faces={"facing": "front", "facing_angle": 90.0}, size=0.01, depth=0.001)


def test_the_surface_is_in_world_space_whatever_the_object_transform(bridge):
    plate(bridge)
    bridge.ok("transform", name="Plate", location=[1.0, -2.0, 0.5], rotation=[0.0, 0.0, 30.0])
    before = volume("Plate")
    plane = {"origin": [1.0, -2.0, 0.51], "normal": [0, 0, 1]}
    result = bridge.ok("engrave", name="Plate", text="10", plane=plane, size=0.03, depth=0.002)
    expected = font_area("10", 0.03) * 0.002
    assert abs((before - volume("Plate")) / expected - 1.0) < 0.01 and result["manifold"] is True
    message = bridge.refuse("engrave", "failed", name="Plate", text="10", plane={"origin": [1.0, -2.0, 0.6], "normal": [0, 0, 1]}, size=0.03, depth=0.002)
    assert "did not change" in message
    close(volume("Plate"), before - expected, expected * 0.02)


def test_every_zodiac_sign_and_planet_symbol_engraves_cleanly_with_its_own_area(bridge):
    plate(bridge, "Plate", (0.3, 0.3, 0.02))
    size, depth = 0.04, 0.001
    for index, name in enumerate(ZODIAC + PLANETS):
        before = volume("Plate")
        origin = [-0.12 + 0.06 * (index % 5), 0.12 - 0.06 * (index // 5), 0.01]
        result = bridge.ok("engrave", name="Plate", text="{" + name + "}", plane={"origin": origin, "normal": [0, 0, 1]}, size=size, depth=depth, align="left", valign="baseline")
        expected = glyph_area(name, size) * depth
        assert abs((before - volume("Plate")) / expected - 1.0) < 0.01, name
        assert result["manifold"] is True, name
    assert degenerate_triangles("Plate") == 0 and is_closed_manifold("Plate")


def test_unicode_signs_and_tokens_give_the_same_cut(bridge):
    assert len(ZODIAC) == 12 and len(PLANETS) == 11 and len(CHARACTERS) == 23
    plate(bridge, "A")
    plate(bridge, "B")
    plane = {"origin": [0, 0, 0.01], "normal": [0, 0, 1]}
    first = bridge.ok("engrave", name="A", text="♈☉", plane=plane, size=0.03, depth=0.002)
    second = bridge.ok("engrave", name="B", text="{aries}{sun}", plane=plane, size=0.03, depth=0.002)
    close(first["volume_change"], second["volume_change"], 1e-12)


def test_a_curve_path_carries_the_text_like_a_plane_when_it_is_straight(bridge):
    plate(bridge)
    before = volume("Plate")
    path = {"waypoints": [[-0.09, 0, 0.01], [0.09, 0, 0.01]], "normal": [0, 0, 1]}
    result = bridge.ok("engrave", name="Plate", text="10", curve=path, size=0.03, depth=0.002, offset=0.06)
    expected = font_area("10", 0.03) * 0.002
    assert abs((before - volume("Plate")) / expected - 1.0) < 0.01
    assert result["surface"] == "curve" and is_closed_manifold("Plate") and degenerate_triangles("Plate") == 0


def test_text_follows_a_bent_curve_and_refuses_to_run_off_its_end(bridge):
    plate(bridge, "Plate", (0.3, 0.3, 0.02))
    arc = [[0.12 * math.cos(math.radians(a)), 0.12 * math.sin(math.radians(a)), 0.01] for a in range(0, 91, 3)]
    result = bridge.ok("engrave", name="Plate", text="10 {leo}", curve={"waypoints": arc, "normal": [0, 0, 1]}, size=0.012, depth=0.001, offset=0.05, tolerance=0.00005)
    assert result["manifold"] is True and degenerate_triangles("Plate") == 0 and result["volume_change"] < 0
    message = bridge.refuse("engrave", "bad_args", name="Plate", text="100000000", curve={"waypoints": arc, "normal": [0, 0, 1]}, size=0.02, depth=0.001)
    assert "past the end" in message


def test_a_repeat_numbers_a_scale_around_a_ring(bridge):
    ring(bridge)
    before = volume("Ring")
    result = bridge.ok(
        "engrave",
        name="Ring",
        text="{n}",
        **band(angle=0.0),
        size=0.004,
        depth=0.0006,
        shift=HEIGHT / 2,
        repeat={"count": 12, "step": 30.0, "number_start": 0, "number_step": 30},
        tolerance=0.00005,
    )
    expected = sum(font_area(str(30 * index), 0.004) for index in range(12)) * (0.0006 - 0.0006 ** 2 / (2 * RADIUS))
    assert abs((before - volume("Ring")) / expected - 1.0) < 0.04, (before - volume("Ring"), expected)
    assert result["instances"] == 12 and result["manifold"] is True and degenerate_triangles("Ring") == 0


def test_repeating_the_same_mark_gives_copies_at_each_step(bridge):
    plate(bridge)
    before = volume("Plate")
    bridge.ok("engrave", name="Plate", text="{sun}", plane={"origin": [-0.06, 0, 0.01], "normal": [0, 0, 1]}, size=0.015, depth=0.001, repeat={"count": 4, "step": 0.04})
    single = glyph_area("sun", 0.015) * 0.001
    assert abs((before - volume("Plate")) / (4 * single) - 1.0) < 0.01


def test_a_font_file_from_the_workspace_replaces_the_bundled_font(bridge):
    source = os.path.join(bpy.utils.system_resource("DATAFILES", path="fonts"), "DejaVuSansMono.woff2")
    shutil.copy(source, os.path.join(bridge.workspace, "mono.woff2"))
    plate(bridge)
    before = volume("Plate")
    bridge.ok("engrave", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 1]}, size=0.03, depth=0.002, font="mono.woff2")
    expected = font_area("10", 0.03, bpy.data.fonts.load(source)) * 0.002
    assert abs((before - volume("Plate")) / expected - 1.0) < 0.01
    assert len(bpy.data.fonts) <= 2
    bridge.refuse("engrave", "not_found", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 1]}, size=0.03, depth=0.002, font="missing.ttf")
    bridge.refuse("engrave", "forbidden", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 1]}, size=0.03, depth=0.002, font="mono.txt")


def test_engraving_keeps_the_material_slots_and_gives_the_new_faces_the_material_beneath(bridge):
    plate(bridge)
    bridge.ok("add_material", name="Brass", base_color=[0.6, 0.4, 0.1])
    bridge.ok("assign_material", name="Plate", material="Brass")
    bridge.ok("engrave", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 1]}, size=0.03, depth=0.002)
    mesh = bpy.data.objects["Plate"].data
    assert [slot.material.name if slot.material else None for slot in bpy.data.objects["Plate"].material_slots] == ["Brass"]
    assert {polygon.material_index for polygon in mesh.polygons} == {0}


def test_the_layout_options_move_the_text(bridge):
    from blendworks_bridge.textlayout import text_shapes

    class Context:
        scene = bpy.context.scene

        def depsgraph(self):
            return bpy.context.evaluated_depsgraph_get()

    def extent(**options):
        values = {"text": "10", "size": 0.03, "spacing": 1.0, "font": None, "align": "centre", "valign": "baseline", "rotation": 0.0}
        values.update(options)
        shapes, width = text_shapes(Context(), values["text"], values["size"], values["spacing"], values["font"], values["align"], values["valign"], values["rotation"])
        xs = [x for outline, _ in shapes for x, _ in outline]
        ys = [y for outline, _ in shapes for _, y in outline]
        return min(xs), max(xs), min(ys), max(ys), width

    centred, left, right = extent(), extent(align="left"), extent(align="right")
    close(centred[0], -centred[1], 1e-9)
    close(left[0], 0.0, 1e-9)
    close(right[1], 0.0, 1e-9)
    assert extent(spacing=2.0)[4] > centred[4] * 1.2
    middle = extent(valign="middle")
    close(middle[2] + CAP_HEIGHT * 0.03 / 2, centred[2], 1e-9)
    turned = extent(rotation=90.0)
    close(turned[1] - turned[0], centred[3] - centred[2], 1e-9)


def test_engrave_refuses_what_does_not_fit(bridge):
    plate(bridge)
    plane = {"origin": [0, 0, 0.01], "normal": [0, 0, 1]}
    base = dict(name="Plate", text="10", plane=plane, size=0.01)
    bridge.refuse("engrave", "bad_args", **base)
    bridge.refuse("engrave", "bad_args", **base, depth=0.001, height=0.001)
    bridge.refuse("engrave", "bad_args", name="Plate", text="10", size=0.01, depth=0.001)
    bridge.refuse("engrave", "bad_args", **base, depth=0.001, cylinder={"radius": 0.1})
    bridge.refuse("engrave", "bad_args", **base, depth=0.001, repeat={"count": 3, "step": 0.0})
    bridge.refuse("engrave", "bad_args", **base, depth=0.001, repeat={"count": 3, "step": 0.1, "number_step": 1})
    bridge.refuse("engrave", "bad_args", name="Plate", text="{n}", plane=plane, size=0.01, depth=0.001)
    bridge.refuse("engrave", "bad_args", name="Plate", text="{nothing}", plane=plane, size=0.01, depth=0.001)
    bridge.refuse("engrave", "bad_args", name="Plate", text="   ", plane=plane, size=0.01, depth=0.001)
    bridge.refuse("engrave", "bad_args", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 0]}, size=0.01, depth=0.001)
    bridge.refuse("engrave", "bad_args", name="Plate", text="10", curve={"waypoints": [[0, 0, 0], [1, 0, 0]], "normal": [1, 0, 0]}, size=0.01, depth=0.001)
    bridge.refuse("engrave", "bad_args", name="Plate", text="10", curve={"object": "Plate", "waypoints": [[0, 0, 0], [1, 0, 0]]}, size=0.01, depth=0.001)
    bridge.refuse("engrave", "not_found", name="Ghost", text="10", plane=plane, size=0.01, depth=0.001)
    bridge.ok("curve_from_points", name="Line", points=[[0, 0, 0], [1, 0, 0]])
    bridge.refuse("engrave", "bad_args", name="Line", text="10", plane=plane, size=0.01, depth=0.001)
    assert volume("Plate") > 0


def test_an_engraving_that_fails_after_the_cut_is_rolled_back(bridge):
    from blendworks_bridge import engraving as engrave_command
    from blendworks_bridge.errors import failed

    plate(bridge)
    before = volume("Plate")
    count = len(bpy.data.objects["Plate"].data.vertices)
    original = engrave_command.clean_object

    def broken(*arguments, **keywords):
        raise failed("the clean-up broke")

    engrave_command.clean_object = broken
    try:
        message = bridge.refuse("engrave", "failed", name="Plate", text="10", plane={"origin": [0, 0, 0.01], "normal": [0, 0, 1]}, size=0.03, depth=0.002)
    finally:
        engrave_command.clean_object = original
    assert "clean-up broke" in message
    close(volume("Plate"), before, 1e-12)
    assert len(bpy.data.objects["Plate"].data.vertices) == count
    assert not [obj for obj in bpy.data.objects if obj.name.startswith("blendworks_engrave")]


def test_a_failed_engraving_leaves_the_mesh_as_it_was(bridge):
    plate(bridge)
    before = volume("Plate")
    count = len(bpy.data.objects["Plate"].data.vertices)
    bridge.refuse("engrave", "bad_args", name="Plate", text="10", curve={"waypoints": [[0, 0, 0.01], [0.001, 0, 0.01]], "normal": [0, 0, 1]}, size=0.03, depth=0.001)
    close(volume("Plate"), before, 1e-12)
    assert len(bpy.data.objects["Plate"].data.vertices) == count
    assert not [obj for obj in bpy.data.objects if obj.name.startswith("blendworks_engrave")]


run(globals())
