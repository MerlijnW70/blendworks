import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run

CRATE_MIN = [-0.5, -0.5, -0.4]
CRATE_MAX = [0.5, 0.5, 0.4]


def build_crate(bridge):
    bridge.ok("add_primitive", type="cube", name="Crate", size=1.0)
    bridge.ok("transform", name="Crate", scale=[1.0, 1.0, 0.8])
    bridge.ok("apply_transform", name="Crate")
    bridge.ok("bevel", name="Crate", width=0.02, segments=2)
    bridge.ok("inset", name="Crate", facing="up", facing_angle=5.0, thickness=0.08)
    bridge.ok("extrude", name="Crate", facing="up", facing_angle=5.0, distance=-0.6)
    bridge.ok("add_material", name="Wood", base_color=[0.45, 0.28, 0.12], roughness=0.7)
    bridge.ok("assign_material", name="Crate", material="Wood")
    uv = bridge.ok("uv_smart_project", name="Crate")
    assert uv["overlap"] < 0.01 and uv["outside"] is False
    origin = bridge.ok("set_origin", name="Crate", to="bottom_centre")
    close(origin["origin"], [0.0, 0.0, -0.4])


def test_crate_round_trips_through_glb(bridge):
    build_crate(bridge)
    built = bridge.info("Crate")
    close(built["bounds"]["min"], CRATE_MIN)
    close(built["bounds"]["max"], CRATE_MAX)
    close(built["dimensions"], [1.0, 1.0, 0.8])
    triangles = built["mesh"]["triangles"]
    assert triangles > 12
    exported = bridge.ok("export", path="crate.glb")
    assert exported["objects"] == ["Crate"] and exported["bytes"] > 0
    bridge.ok("new_scene")
    imported = bridge.ok("import", path="crate.glb")
    assert imported["objects"] == ["Crate"]
    info = bridge.ok("scene_info")
    assert info["totals"]["triangles"] == triangles
    crate = bridge.info("Crate")
    assert crate["mesh"]["triangles"] == triangles
    close(crate["bounds"]["min"], CRATE_MIN)
    close(crate["bounds"]["max"], CRATE_MAX)
    close(crate["location"], [0.0, 0.0, -0.4])
    assert crate["materials"] == ["Wood"]
    assert crate["uv_layers"] != []


run(globals())
