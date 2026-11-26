import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from cover_helpers import accessor_values, attribute_of, glb_document, instanced_translations, make_plane, make_soil, points_of, sorted_rows, workspace_file

INSTANCING = "EXT_mesh_gpu_instancing"


def small_cover(bridge, wind=True):
    make_plane(bridge, size=6.0)
    make_soil(bridge)
    populations = [
        {"name": "grass", "element": "grass", "density": 3.0, "variants": 2, "form": "auto", "card_distance": 2.0, "triangles": 120},
        {"name": "stones", "element": "pebble", "density": 1.0, "variants": 2, "triangles": 80},
    ]
    return bridge.ok("ground_cover", target="Ground", populations=populations, point=[0.0, -3.0, 1.0], near=2.0, wind=wind, seed=4)


def y_up(points):
    return numpy.column_stack([points[:, 0], points[:, 2], -points[:, 1]])


def test_instances_export_with_gpu_instancing_and_round_trip_through_import(bridge):
    cover = small_cover(bridge)
    result = bridge.ok("ground_cover_export", path="cover.glb", name="GroundCover", with_objects=["Ground"])
    assert result["count"] == cover["count"] == result["instances"]
    assert INSTANCING in result["extensions_used"]
    document, binary = glb_document(workspace_file(bridge, "cover.glb"))
    assert INSTANCING in document["extensionsUsed"]
    placed = numpy.concatenate([points_of("GroundCover_grass"), points_of("GroundCover_stones")])
    exported = instanced_translations(document, binary)
    assert exported.shape == placed.shape
    assert numpy.allclose(sorted_rows(exported), sorted_rows(y_up(placed)), atol=2e-4)
    for node in document["nodes"]:
        extension = node.get("extensions", {}).get(INSTANCING)
        if extension:
            rotations = accessor_values(document, binary, extension["attributes"]["ROTATION"])
            assert numpy.allclose(numpy.linalg.norm(rotations, axis=1), 1.0, atol=1e-3)
            assert "SCALE" in extension["attributes"]
    colored = [primitive for mesh in document["meshes"] for primitive in mesh["primitives"] if "COLOR_0" in primitive["attributes"]]
    assert colored and result["primitives_with_color"] == len(colored)
    before = {obj.name for obj in bpy.data.objects}
    bridge.ok("import", path="cover.glb")
    imported = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH" and obj.name.split(".")[0] != "Ground"]
    assert len(imported) == cover["count"]
    locations = numpy.array([list(obj.matrix_world.translation) for obj in imported])
    assert numpy.allclose(sorted_rows(locations), sorted_rows(placed), atol=2e-4)
    matrices = numpy.concatenate([attribute_of(name, "gc_transform", 16).reshape(-1, 4, 4).transpose(0, 2, 1) for name in ("GroundCover_grass", "GroundCover_stones")])
    for obj in imported:
        world = numpy.array(obj.matrix_world)
        match = numpy.argmin(numpy.linalg.norm(matrices[:, :3, 3] - world[:3, 3], axis=1))
        assert numpy.allclose(world[:3, :3], matrices[match, :3, :3], atol=1e-3), (obj.name, world, matrices[match])


def test_realized_lods_halve_the_elements_per_level_and_switch_to_cards(bridge):
    small_cover(bridge, wind=False)
    result = bridge.ok("ground_cover_export", path="lods.glb", name="GroundCover", mode="realized", levels=3)
    levels = result["levels"]
    assert set(levels) == {f"GroundCover_{population}_LOD{level}" for population in ("grass", "stones") for level in range(3)}
    grass = [levels[f"GroundCover_grass_LOD{level}"]["triangles"] for level in range(3)]
    assert grass[0] > 4 * grass[1] > 0 and grass[2] < grass[1]
    stones = [levels[f"GroundCover_stones_LOD{level}"]["vertices"] for level in range(3)]
    assert stones[0] > stones[1] > stones[2] > 0
    document, _ = glb_document(workspace_file(bridge, "lods.glb"))
    assert INSTANCING not in document.get("extensionsUsed", [])
    assert {node["name"] for node in document["nodes"]} >= set(levels)
    assert not any(name.endswith(("_LOD0", "_LOD1", "_LOD2")) for name in bpy.data.objects.keys())
    assert result["primitives_with_color"] == 0


def test_ground_cover_export_refuses_other_files_and_objects_without_cover(bridge):
    small_cover(bridge)
    assert ".glb" in bridge.refuse("ground_cover_export", "bad_args", path="cover.fbx", name="GroundCover")
    assert "holds no ground cover" in bridge.refuse("ground_cover_export", "bad_args", path="cover.glb", name="Ground")
    single = bridge.ok("ground_cover_export", path="stones.glb", name="GroundCover_stones")
    assert single["count"] == len(points_of("GroundCover_stones")) == single["instances"]


run(globals())
