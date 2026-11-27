import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from engrave_checks import shape_counts
from harness import run
from kit_helpers import is_closed_manifold

from blendworks_bridge import engraving

TOP = 0.003
MINOR = {"length": 0.004, "depth": 0.0004}
MAJOR = {"length": 0.008, "depth": 0.0008}


def ring(bridge, name="Ring"):
    bridge.ok("sweep", name=name, preset="rounded_rectangle", width=0.06, height=2 * TOP, corner_radius=0.0009, segments=2, circle={"centre": [0, 0, 0], "radius": 0.15, "tolerance": 0.00006})


def floors(name):
    bm = bmesh.new()
    bm.from_mesh(bpy.data.objects[name].data)
    try:
        bm.normal_update()
        floor = {face for face in bm.faces if face.normal.z > 0.999 and face.calc_center_median().z < TOP - 1e-5}
        marks = []
        while floor:
            group, todo = set(), [floor.pop()]
            while todo:
                face = todo.pop()
                group.add(face)
                for edge in face.edges:
                    for other in edge.link_faces:
                        if other in floor:
                            floor.discard(other)
                            todo.append(other)
            points = [vert.co for face in group for vert in face.verts]
            reference = math.atan2(points[0].y, points[0].x)
            turns = [(math.atan2(point.y, point.x) - reference + math.pi) % math.tau - math.pi for point in points]
            middle = math.degrees(reference + (min(turns) + max(turns)) / 2.0) % 360.0
            radii = [math.hypot(point.x, point.y) for point in points]
            marks.append({"angle": middle, "depth": TOP - sum(point.z for point in points) / len(points), "length": max(radii) - min(radii)})
        return sorted(marks, key=lambda mark: mark["angle"])
    finally:
        bm.free()


def test_360_marks_with_majors_every_10_degrees_are_cut_in_one_boolean(bridge):
    ring(bridge)
    calls = []
    original = engraving.apply_cutter

    def counted(*arguments):
        calls.append(arguments[4])
        return original(*arguments)

    engraving.apply_cutter = counted
    try:
        result = bridge.ok("engrave_scale", name="Ring", ring={"centre": [0, 0, TOP], "radius": 0.165}, start=0, end=360, step=1, width=0.0004, **MINOR, classes=[{"every": 10, **MAJOR}])
    finally:
        engraving.apply_cutter = original
    assert len(calls) == 1, calls
    assert result["marks"] == 360 and result["classes"] == [{"every": 1, "marks": 324}, {"every": 10, "marks": 36}], result["classes"]
    assert result["manifold"] is True and is_closed_manifold("Ring") and shape_counts("Ring")["slivers"] == 0
    marks = floors("Ring")
    assert len(marks) == 360, len(marks)
    for index, mark in enumerate(marks):
        major = index % 10 == 0
        expected = MAJOR if major else MINOR
        assert abs(mark["angle"] - index) < 0.01, (index, mark)
        assert abs(mark["depth"] - expected["depth"]) < 1e-6, (index, mark)
        assert abs(mark["length"] - expected["length"]) < 2e-5, (index, mark)


def test_quadrant_mirroring_repeats_a_quarter_scale_four_times(bridge):
    ring(bridge)
    result = bridge.ok("engrave_scale", name="Ring", ring={"centre": [0, 0, TOP], "radius": 0.165}, start=0, end=90, step=5, mirror="quadrants", width=0.0005, **MINOR, classes=[{"every": 3, **MAJOR}])
    expected = sorted({round(value % 360.0, 6) for source in range(0, 91, 5) for value in (source, 180 - source, 180 + source, 360 - source)})
    assert result["marks"] == len(expected) == 72
    marks = floors("Ring")
    assert [round(mark["angle"]) % 360 for mark in marks] == [round(value) for value in expected]
    for mark in marks:
        half = round(mark["angle"]) % 180
        offset = half if half <= 90 else 180 - half
        major = (offset // 5) % 3 == 0
        assert abs(mark["depth"] - (MAJOR if major else MINOR)["depth"]) < 1e-6, (mark, offset)


def test_a_count_spreads_marks_and_a_cylinder_scale_runs_along_the_axis(bridge):
    ring(bridge)
    result = bridge.ok("engrave_scale", name="Ring", ring={"centre": [0, 0, TOP], "radius": 0.165}, start=10, end=50, count=5, width=0.0005, **MINOR)
    assert result["angles"] == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert [round(mark["angle"], 2) for mark in floors("Ring")] == [10.0, 20.0, 30.0, 40.0, 50.0]
    bridge.ok("add_primitive", type="cylinder", name="Drum", radius=0.05, depth=0.04, segments=128)
    band = bridge.ok("engrave_scale", name="Drum", cylinder={"radius": 0.05, "centre": [0, 0, 0]}, step=30, place="centre", width=0.0005, length=0.01, depth=0.0005)
    assert band["marks"] == 12 and band["manifold"] is True and band["volume_change"] < 0


def test_engrave_scale_refuses_what_it_cannot_build(bridge):
    ring(bridge)
    surface = {"ring": {"centre": [0, 0, TOP], "radius": 0.165}}
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, step=1, depth=0.0004, height=0.0004)
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, step=1, count=10, depth=0.0004)
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, step=0, depth=0.0004)
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, start=0, end=90, step=-1, depth=0.0004)
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, step=0.05, depth=0.0004)
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, step=1, depth=0.0004, classes=[{"every": 10, "height": 0.001}])
    bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, step=1, depth=0.0004, classes=[{"every": 10}, {"every": 10}])
    bridge.refuse("engrave_scale", "bad_args", name="Ring", step=1, depth=0.0004)
    message = bridge.refuse("engrave_scale", "bad_args", name="Ring", **surface, start=-36000, end=36000, step=1e-9, depth=0.0004)
    assert "Raise step" in message, message


run(globals())
