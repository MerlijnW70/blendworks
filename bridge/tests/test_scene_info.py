import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from harness import close, run

from blendworks_bridge.util import bounds_of, evaluated_points

COUNT = 1500


def crowd(count=COUNT):
    collection = bpy.context.scene.collection
    template = bpy.data.meshes.new("unit")
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=1.0)
    builder.to_mesh(template)
    builder.free()
    for index in range(count):
        prefix = "Bolt" if index % 3 == 0 else "Plate"
        obj = bpy.data.objects.new(f"{prefix}{index:04d}", template)
        obj.location = (index % 40, index // 40, 0.0)
        collection.objects.link(obj)


def test_the_default_is_totals_and_the_first_100_objects_with_a_note(bridge):
    crowd()
    started = time.perf_counter()
    info = bridge.ok("scene_info")
    elapsed = time.perf_counter() - started
    assert info["detail"] == "objects"
    assert info["totals"]["objects"] == COUNT and info["totals"]["triangles"] == COUNT * 12
    assert info["totals"]["by_type"] == {"mesh": COUNT}
    assert len(info["objects"]) == 100
    assert info["page"] == {"offset": 0, "limit": 100, "returned": 100, "matched": COUNT, "next_offset": 100}
    assert any("offset 100" in note for note in info["notes"])
    names = [entry["name"] for entry in info["objects"]]
    assert names == sorted(names) and names[0] == "Bolt0000"
    close(info["bounds"]["min"], [-0.5, -0.5, -0.5])
    close(info["bounds"]["max"], [39.5, (COUNT - 1) // 40 + 0.5, 0.5])
    size = len(json.dumps(info))
    print(f"scene_info over {COUNT} objects: {size} bytes in {elapsed:.2f} s")
    assert size < 64_000


def test_offsets_walk_every_object_exactly_once(bridge):
    crowd()
    seen = []
    offset = 0
    while offset is not None:
        info = bridge.ok("scene_info", limit=400, offset=offset)
        seen.extend(entry["name"] for entry in info["objects"])
        offset = info["page"]["next_offset"]
    assert seen == sorted(obj.name for obj in bpy.data.objects)
    last = bridge.ok("scene_info", limit=400, offset=1200)
    assert last["page"]["returned"] == 300 and last["page"]["next_offset"] is None and "notes" not in last
    past = bridge.ok("scene_info", offset=5000)
    assert past["objects"] == [] and "past the 1500" in past["notes"][0]


def test_a_glob_filters_the_page_but_not_the_totals(bridge):
    crowd()
    info = bridge.ok("scene_info", names="Bolt*", limit=1000)
    assert info["page"]["matched"] == 500 and info["page"]["names"] == "Bolt*"
    assert all(entry["name"].startswith("Bolt") for entry in info["objects"])
    assert info["totals"]["objects"] == COUNT
    single = bridge.ok("scene_info", names="Plate0001")
    assert [entry["name"] for entry in single["objects"]] == ["Plate0001"]
    assert bridge.ok("scene_info", names="Nothing*")["objects"] == []
    assert bridge.ok("scene_info", names="bolt*")["page"]["matched"] == 0


def test_summary_and_full_detail(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.ok("add_material", name="Steel", base_color=[0.5, 0.5, 0.5])
    bridge.ok("assign_material", name="Box", material="Steel")
    bpy.data.objects["Box"]["part"] = "lid"
    summary = bridge.ok("scene_info", detail="summary")
    assert "objects" not in summary and "page" not in summary
    assert summary["totals"]["objects"] == 1 and summary["materials"] == ["Steel"]
    full = bridge.ok("scene_info", detail="full")
    box = full["objects"][0]
    assert box["custom_properties"] == {"part": "lid"} and box["collections"] == ["Scene Collection"]
    assert box["data"] == "Box" and box["vertex_groups"] == [] and box["shape_keys"] == []
    assert [entry["name"] for entry in full["material_details"]] == ["Steel"]


def test_bounds_match_the_exact_vertices_of_rotated_modified_objects(bridge):
    bridge.ok("add_primitive", type="cylinder", name="Tilted", segments=12)
    bridge.ok("transform", name="Tilted", rotation=[30.0, 15.0, 45.0], scale=[1.0, 2.0, 0.5], location=[1.0, -2.0, 3.0])
    bridge.ok("solidify", name="Tilted", thickness=0.2, apply=False)
    expected = bounds_of(evaluated_points(bpy.data.objects["Tilted"], bpy.context.evaluated_depsgraph_get()))
    info = bridge.info("Tilted")
    close(info["bounds"]["min"], list(expected[0]), 1e-5)
    close(info["bounds"]["max"], list(expected[1]), 1e-5)
    close(bridge.ok("scene_info")["bounds"]["min"], list(expected[0]), 1e-5)


def test_scene_info_refuses_bad_paging(bridge):
    bridge.refuse("scene_info", "bad_args", limit=0)
    bridge.refuse("scene_info", "bad_args", limit=1001)
    bridge.refuse("scene_info", "bad_args", offset=-1)
    bridge.refuse("scene_info", "bad_args", detail="everything")
    bridge.refuse("scene_info", "bad_args", names="")


run(globals())
