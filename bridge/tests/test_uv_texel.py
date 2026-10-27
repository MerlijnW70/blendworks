import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run, snapshot

from blendworks_bridge.commands import uv_pack as uv_pack_command
from blendworks_bridge.commands.uv import GRID, triangle_cells


def uv_coordinates(name):
    mesh = bpy.data.objects[name].data
    return [tuple(round(value, 6) for value in item.uv) for item in mesh.uv_layers.active.data]


def shared_overlap(names):
    counts = {}
    for name in names:
        mesh = bpy.data.objects[name].data
        uvs = [tuple(item.uv) for item in mesh.uv_layers.active.data]
        cells = set()
        for polygon in mesh.polygons:
            corners = [uvs[index] for index in polygon.loop_indices]
            for second in range(1, len(corners) - 1):
                cells.update(triangle_cells((corners[0], corners[second], corners[second + 1])))
        for cell in cells:
            counts[cell] = counts.get(cell, 0) + 1
    return sum(1 for value in counts.values() if value > 1) / max(len(counts), 1), len(counts) / (GRID * GRID)


def test_uv_info_reports_hand_worked_texel_density(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    density = bridge.ok("uv_info", name="Sheet")["texel_density"]
    assert density == {"texture_size": 1024, "mean": 512.0, "min": 512.0, "max": 512.0}
    assert bridge.ok("uv_info", name="Sheet", texture_size=2048)["texel_density"]["mean"] == 1024.0
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    assert bridge.ok("uv_info", name="Box")["texel_density"]["mean"] == 256.0
    bridge.refuse("uv_info", "bad_args", name="Box", texture_size=0)


def test_smart_project_reaches_a_texel_density(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    result = bridge.ok("uv_smart_project", name="Sheet", texel_density=256.0, island_margin=0.0)
    close(result["texel_density"]["mean"], 256.0, 0.5)
    close(result["uv_area"], 0.25, 1e-3)
    assert result["outside"] is False
    result = bridge.ok("uv_smart_project", name="Sheet", texel_density=2048.0, island_margin=0.0)
    close(result["texel_density"]["mean"], 2048.0, 2.0)
    assert result["outside"] is True
    bridge.refuse("uv_smart_project", "bad_args", name="Sheet", texel_density=0.0)


def test_unwrap_reaches_a_texel_density_and_margin_is_a_share(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    result = bridge.ok("uv_unwrap", name="Box", seam_angle=60.0, texel_density=200.0, texture_size=512, margin=0.02)
    assert result["texel_density"]["texture_size"] == 512
    close(result["texel_density"]["mean"], 200.0, 1.0)
    assert result["overlap"] == 0.0
    tight = bridge.ok("uv_unwrap", name="Box", seam_angle=60.0, margin=0.0)["uv_area"]
    loose = bridge.ok("uv_unwrap", name="Box", seam_angle=60.0, margin=0.1)["uv_area"]
    assert loose < tight


def two_boxes(bridge):
    bridge.ok("add_primitive", type="cube", name="Small", size=1.0)
    bridge.ok("add_primitive", type="cube", name="Large", size=2.0)
    bridge.ok("transform", name="Large", location=[3.0, 0.0, 0.0])
    for name in ("Small", "Large"):
        bridge.ok("uv_smart_project", name=name, island_margin=0.0)


def test_uv_pack_shares_one_atlas_at_one_density(bridge):
    two_boxes(bridge)
    result = bridge.ok("uv_pack", names=["Small", "Large"], margin=0.01)
    assert result["shared"] is True
    small, large = result["objects"]
    close(small["texel_density"]["mean"], large["texel_density"]["mean"], large["texel_density"]["mean"] * 0.01)
    assert not small["outside"] and not large["outside"]
    overlap, coverage = shared_overlap(["Small", "Large"])
    assert overlap == 0.0 and coverage > 0.6, (overlap, coverage)
    loose = bridge.ok("uv_pack", names=["Small", "Large"], margin=0.08)["objects"]
    assert loose[0]["uv_area"] + loose[1]["uv_area"] < small["uv_area"] + large["uv_area"]


def test_uv_pack_separately_and_at_a_fixed_density(bridge):
    two_boxes(bridge)
    result = bridge.ok("uv_pack", names=["Small", "Large"], shared=False, rotate=False)
    for entry in result["objects"]:
        assert entry["overlap"] == 0.0 and entry["coverage"] > 0.5, entry
    assert shared_overlap(["Small", "Large"])[0] > 0.5
    result = bridge.ok("uv_pack", names=["Small", "Large"], texel_density=100.0)
    for entry in result["objects"]:
        close(entry["texel_density"]["mean"], 100.0, 0.5)
    assert shared_overlap(["Small", "Large"])[0] == 0.0


def test_uv_pack_refusals_and_failures_leave_the_uvs(bridge):
    two_boxes(bridge)
    bridge.ok("add_primitive", type="cube", name="Shared")
    bridge.ok("duplicate", name="Shared", new_name="Twin", linked=True)
    bridge.ok("mesh_from_data", name="Bare", vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], faces=[[0, 1, 2]])
    bridge.ok("add_light", type="point", name="Lamp")
    bpy.context.view_layer.update()
    before = (snapshot(), uv_coordinates("Small"), uv_coordinates("Large"))
    bridge.refuse("uv_pack", "not_found", names=["Ghost"])
    bridge.refuse("uv_pack", "bad_args", names=["Lamp"])
    bridge.refuse("uv_pack", "bad_args", names=["Bare"])
    bridge.refuse("uv_pack", "bad_args", names=["Small", "Small"])
    bridge.refuse("uv_pack", "bad_args", names=["Twin"])
    bridge.refuse("uv_pack", "bad_args", names=["Small"], margin=0.9)
    bridge.refuse("uv_pack", "bad_args", names=[])
    original = uv_pack_command.pack

    def broken(*args):
        original(*args)
        raise RuntimeError("injected pack failure")

    uv_pack_command.pack = broken
    try:
        bridge.refuse("uv_pack", "failed", names=["Small", "Large"])
    finally:
        uv_pack_command.pack = original
    assert (snapshot(), uv_coordinates("Small"), uv_coordinates("Large")) == before


if __name__ == "__main__":
    run(globals())
