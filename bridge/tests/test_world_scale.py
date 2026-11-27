import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run

from blendworks_bridge import limit_base, limits, limits_parts, limits_parts_more, plan
from blendworks_bridge.commands import validate as validate_command
from blendworks_bridge.registry import COMMANDS
from blendworks_bridge.schema import bounds

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LIMITS_DOC = os.path.join(REPO, "docs", "LIMITS.md")
FAR = 150_000.0
PLACEMENT_ERROR = 0.0079


def test_landscape_values_that_were_refused_are_accepted(bridge):
    bridge.ok("add_primitive", type="cube", name="far", location=[FAR, -FAR, 10.0], size=1.0)
    bridge.ok("transform", name="far", location=[-FAR, FAR, 2_000.0])
    bridge.ok("heightfield", name="wide", size=[40_000.0, 40_000.0], resolution=5, height=4_000.0, scale=30_000.0)
    bridge.ok("add_camera", name="eye", location=[FAR, 0.0, 1_500.0], target=[0.0, 0.0, 0.0])
    bridge.ok("camera_setup", name="eye", clip_start=0.5, clip_end=300_000.0)
    haze = bridge.ok("atmosphere", visibility=300_000.0, height_falloff=2_500.0)
    assert haze["visibility"] == 300_000.0
    bridge.ok("erode", name="wide", mode="thermal", iterations=1, timeout_seconds=600)
    bridge.ok("noise_displace", name="wide", amplitude=1_500.0, scale=20_000.0, seed=1)
    budget = COMMANDS["ground_cover"].schema["properties"]["budget"]
    assert budget["maximum"] == limits.MAX_COVER_INSTANCES and budget["x-limits"]["maximum"] == "cover_instances"


def test_old_world_edge_is_now_inside_and_the_new_one_still_refuses(bridge):
    bridge.ok("add_primitive", type="cube", name="edge", location=[limits.MAX_COORDINATE, 0.0, 0.0], size=1.0)
    message = bridge.refuse("transform", "bad_args", name="edge", location=[limits.MAX_COORDINATE * 1.01, 0.0, 0.0])
    assert "args.location[0]" in message and "202000" in message and "limit coordinate" in message, message


def test_placement_error_at_150_km_stays_under_8_mm(bridge):
    wanted = [(FAR + 0.3217, -FAR + 0.7731, 1234.5678), (-FAR - 0.0123, FAR - 0.4567, 0.0042), (FAR, FAR, -12.25)]
    for index, location in enumerate(wanted):
        bridge.ok("add_primitive", type="cube", name=f"p{index}", location=list(location), size=0.5)
        bridge.ok("transform", name=f"p{index}", location=list(location))
        placed = bpy.data.objects[f"p{index}"].location
        error = max(abs(placed[axis] - location[axis]) for axis in range(3))
        assert error < PLACEMENT_ERROR, (location, tuple(placed), error)
    bridge.ok("add_primitive", type="cube", name="neighbour", size=0.5)
    bridge.ok("transform", name="neighbour", location=[FAR + 0.05, FAR, -12.25])
    gap = bpy.data.objects["neighbour"].location.x - bpy.data.objects["p2"].location.x
    assert abs(gap - 0.05) < 2 * PLACEMENT_ERROR, gap


def test_every_schema_bound_comes_from_a_named_limit_with_a_reason(bridge):
    with open(LIMITS_DOC, encoding="utf-8") as handle:
        doc = handle.read()
    problems = []
    for name in sorted(COMMANDS):
        for where, keyword, value, tag in bounds(COMMANDS[name].schema):
            if tag is None:
                problems.append(f"{name} {where} {keyword}={value} has no named limit")
            elif abs(value) != abs(limits.LIMITS[tag].plain()):
                problems.append(f"{name} {where} {keyword}={value} differs from limit {tag}")
    for key, entry in limits.LIMITS.items():
        if entry.kind not in limits.KINDS or len(entry.reason.strip()) < 15:
            problems.append(f"limit {key} has no reason")
        if not re.search(rf"^\| `{re.escape(key)}` \|", doc, re.M):
            problems.append(f"limit {key} is missing from docs/LIMITS.md")
    assert not problems, "\n".join(problems[:40]) + f"\n({len(problems)} in all)"


def test_limits_doc_is_written_from_the_limits(bridge):
    import limits_doc

    with open(LIMITS_DOC, encoding="utf-8") as handle:
        written = handle.read()
    table = [line for line in limits_doc.render().splitlines() if not any(f"`{key}`" in line for key in limits_doc.MACHINE_DEPENDENT)]
    kept = [line for line in written.splitlines() if not any(f"`{key}`" in line for key in limits_doc.MACHINE_DEPENDENT)]
    assert table == kept, "docs/LIMITS.md is out of date: run bridge/tests/limits_doc.py"


def test_equal_quantities_have_equal_limits(bridge):
    """The same physical quantity has the same physical limit in every tool; a memory or time limit may cap it
    lower where the value drives work (erode's brush radius). A quantity is a field name with a unit; shares without
    a unit (a moss height share, a rib height share) are different quantities even with the same field name. "height"
    in metres also names two: the relief of land (heightfield) and the size of a part (sweep, loft, engrave)."""
    tags = {}
    for name in sorted(COMMANDS):
        for where, keyword, value, tag in bounds(COMMANDS[name].schema):
            field = re.sub(r"\[\]", "", where.split(".")[-1])
            if tag is not None and keyword in ("maximum", "exclusiveMaximum") and limits.LIMITS[tag].kind == limits.PHYSICAL:
                unit = limits.LIMITS[tag].unit
                tags.setdefault((field, unit), {}).setdefault(tag, []).append(f"{name}{where[4:]}")
    checked = 0
    for (field, unit), found in sorted(tags.items()):
        if unit and field in ("visibility", "amplitude", "seed", "clip_end", "location", "radius", "width", "depth",
                     "distance", "spacing", "scale", "warp", "strength", "frame", "margin", "level"):
            assert len(found) == 1, (field, unit, found)
            checked += 1
    assert checked >= 15, checked
    relief = {f"{name}{where[4:]}": tag for name in ("heightfield", "noise_displace", "displace_noise")
              for where, keyword, value, tag in bounds(COMMANDS[name].schema) if keyword == "maximum"}
    assert relief["heightfield.height"] == relief["noise_displace.amplitude"] == relief["displace_noise.amplitude"] == "relief", relief


def test_refusals_name_argument_value_limit_and_alternative(bridge):
    message = bridge.refuse("render_preview", "bad_args", resolution=4096)
    for part in ("args.resolution", "4096", "1024", "limit preview_resolution", "render_final"):
        assert part in message, (part, message)
    reply = bridge.call("validate", calls=[{"cmd": "render_preview", "args": {"resolution": 4096}}])
    problem = reply["result"]["problems"][0]
    assert problem["argument"] == "args.resolution" and problem["value"] == 4096, problem
    assert problem["limit"]["name"] == "preview_resolution" and problem["limit"]["value"] == 1024, problem
    assert "render_final" in problem["instead"], problem


def bad_plan():
    return [
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "a", "location": [0.0, 0.0, 500_000.0]}},
        {"cmd": "noise_displace", "args": {"name": "missing", "amplitude": 50_000.0}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "a"}},
        {"cmd": "atmosphere", "args": {"visibility": -5.0, "colour": "blue"}},
        {"cmd": "no_such_tool", "args": {}},
    ]


def test_validate_reports_every_error_of_a_bad_plan_at_once_and_runs_nothing(bridge):
    before = len(bpy.data.objects)
    result = bridge.ok("validate", calls=bad_plan())
    assert result["valid"] is False and result["ran"] == 0
    seen = {(problem["call"], problem["argument"]) for problem in result["problems"]}
    for expected in ((0, "args.location[2]"), (1, "args.name"), (1, "args.amplitude"), (2, "args.name"),
                     (3, "args.visibility"), (3, "args.colour"), (4, "cmd")):
        assert expected in seen, (expected, sorted(seen))
    for problem in result["problems"]:
        assert problem["message"] and "argument" in problem, problem
    assert len(bpy.data.objects) == before
    assert "a" not in bpy.data.objects
    bridge.refuse("validate", "bad_args", calls=[])


def test_validate_accepts_a_plan_whose_later_calls_use_earlier_names(bridge):
    plan = [
        {"cmd": "new_scene", "args": {}},
        {"cmd": "heightfield", "args": {"name": "land", "size": [20_000.0, 20_000.0], "resolution": 5, "height": 900.0}},
        {"cmd": "material_procedural", "args": {"name": "ground", "grass_ground": {}}},
        {"cmd": "assign_material", "args": {"name": "land", "material": "ground"}},
        {"cmd": "add_camera", "args": {"name": "view", "location": [15_000.0, 0.0, 900.0]}},
        {"cmd": "camera_setup", "args": {"name": "view", "clip_end": 200_000.0}},
        {"cmd": "render_final", "args": {"path": "x.png", "camera": "view"}},
    ]
    result = bridge.ok("validate", calls=plan, from_scene=False)
    assert result == {"valid": True, "calls": len(plan), "problems": [], "ran": 0}, result
    assert "land" not in bpy.data.objects
    swapped = [plan[0], plan[3], plan[1], plan[2]]
    later = bridge.ok("validate", calls=swapped, from_scene=False)["problems"]
    assert {(p["call"], p["argument"]) for p in later} == {(1, "args.name"), (1, "args.material")}, later


def test_validate_knows_the_scene_collection_and_renaming_to_the_own_name(bridge):
    plan = [
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "box"}},
        {"cmd": "collection_link", "args": {"collection": "Scene Collection", "names": ["box"]}},
        {"cmd": "rename", "args": {"name": "box", "new_name": "box"}},
        {"cmd": "add_primitive", "args": {"type": "cube", "name": "other"}},
        {"cmd": "rename", "args": {"name": "other", "new_name": "box"}},
    ]
    problems = bridge.ok("validate", calls=plan, from_scene=False)["problems"]
    assert [(p["call"], p["argument"]) for p in problems] == [(4, "args.new_name")], problems
    assert bridge.ok("validate", calls=plan[:3])["valid"] is True


def test_every_limit_module_feeds_the_one_table(bridge):
    assert limits.LIMITS is limit_base.LIMITS
    for module in (limits_parts, limits_parts_more):
        named = {name: value for name, value in vars(module).items() if isinstance(value, (limit_base.FloatLimit, limit_base.IntLimit))}
        assert named and all(getattr(limits, name) is value for name, value in named.items()), module.__name__
    state = plan.PlanState()
    assert state.has("collection", plan.MASTER_COLLECTION) and not state.has("object", "x")
    assert validate_command.validate is COMMANDS["validate"].run


def test_scene_memory_follows_the_memory_this_process_may_use(bridge):
    eight = 8 * 1024 ** 3
    folder = tempfile.mkdtemp(prefix="cgroup-")
    v2 = os.path.join(folder, "memory.max")
    with open(v2, "w", encoding="ascii") as handle:
        handle.write(f"{eight}\n")
    total = limits.available_memory(cgroup_files=(v2,), physical=lambda: 64 * 1024 ** 3)
    assert total == eight
    assert limits.scene_memory(total) == eight // 2
    assert limits.available_memory(cgroup_files=(v2,), physical=lambda: 4 * 1024 ** 3) == 4 * 1024 ** 3
    assert limits.parse_cgroup_limit("max") is None and limits.parse_cgroup_limit("") is None
    assert limits.MAX_SCENE_MEMORY == limits.scene_memory(limits.available_memory())
    assert limits.MAX_COVER_INSTANCES == limits.MAX_SCENE_MEMORY // limits.COVER_INSTANCE_BYTES
    default = COMMANDS["ground_cover"].schema["properties"]["budget"]["default"]
    assert default * limits.COVER_INSTANCE_BYTES <= limits.scene_memory(eight)


def test_timeout_seconds_is_checked_the_same_way_for_scripts(bridge):
    bridge.ok("add_primitive", type="cube", name="t", timeout_seconds=30)
    message = bridge.refuse("add_primitive", "bad_args", type="cube", name="u", timeout_seconds=100_000)
    assert "timeout_seconds" in message and "100000" in message, message


run(globals())
