import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run
from blendworks_bridge.blendfile import content_digest, image_digest
from blendworks_bridge.exporting import keeps_lossy_source

TREE = {"grow": {"name": "oak", "preset": "oak", "seed": 3, "points": 200, "height": 4.0, "limit": 0}, "mesh": {}, "leaves": {"seed": 3, "detail": "low"}}
STANDS = [{"kind": "copse", "centre": [0.0, 0.0], "radius": 9.0}]
WOOD = {"species": ["oak"], "shrubs": ["hazel"], "variants": 1, "points_share": 0.05, "detail": "low", "understorey": False, "shade_ground": False, "workers": 1}


def packed_image(name, value, size=8):
    image = bpy.data.images.new(name, size, size)
    image.pixels.foreach_set(numpy.full(size * size * 4, value, dtype=numpy.float32))
    image.pack()
    return image


def tiled_image(name, values, folder, stem="tile"):
    """A UDIM image of one tile per value, saved as PNG tiles under stem, loaded as a tiled image and packed: one packed
    file per tile. Images made from the same stem share their file paths and differ only in their packed bytes."""
    for index, value in enumerate(values):
        tile = bpy.data.images.new(f"{name}_source_{index}", 8, 8)
        tile.pixels.foreach_set(numpy.full(256, value, dtype=numpy.float32))
        tile.filepath_raw = os.path.join(folder, f"{stem}.{1001 + index}.png")
        tile.file_format = "PNG"
        tile.save()
        bpy.data.images.remove(tile)
    image = bpy.data.images.load(os.path.join(folder, f"{stem}.1001.png"), check_existing=False)
    image.source = "TILED"
    for index in range(1, len(values)):
        image.tiles.new(tile_number=1001 + index)
    image.name = name
    image.pack()
    return image


def test_a_packed_image_digests_its_packed_bytes(bridge):
    first = packed_image("first", 0.25)
    same = packed_image("same", 0.25)
    other = packed_image("other", 0.75)
    assert len(first.packed_files) == 1 and first.packed_file is not None
    assert image_digest(first) == image_digest(same)
    assert image_digest(first) != image_digest(other)
    assert content_digest(first) == content_digest(same)


def test_every_tile_of_a_packed_udim_image_counts_in_its_digest(bridge):
    with tempfile.TemporaryDirectory() as folder:
        tiles = tiled_image("tiles", [0.2, 0.6], folder)
        again = tiled_image("again", [0.2, 0.6], folder)
        changed = tiled_image("changed", [0.2, 0.9], folder)
        assert len(tiles.packed_files) == 2, len(tiles.packed_files)
        assert sorted(packed.tile_number for packed in tiles.packed_files) == [1001, 1002]
        assert image_digest(tiles) == image_digest(again)
        assert image_digest(tiles) != image_digest(changed)
        assert keeps_lossy_source(tiles) is False


def test_export_reads_the_signature_of_packed_sources_through_the_same_api(bridge):
    with tempfile.TemporaryDirectory() as folder:
        found = {}
        for file_format, suffix in (("JPEG", "jpg"), ("PNG", "png")):
            source = bpy.data.images.new(f"source_{suffix}", 8, 8)
            source.pixels.foreach_set(numpy.full(256, 0.5, dtype=numpy.float32))
            source.filepath_raw = os.path.join(folder, f"source.{suffix}")
            source.file_format = file_format
            source.save()
            bpy.data.images.remove(source)
            image = bpy.data.images.load(os.path.join(folder, f"source.{suffix}"), check_existing=False)
            image.pack()
            image.filepath_raw = ""
            found[suffix] = keeps_lossy_source(image)
        assert found == {"jpg": True, "png": False}, found


def test_parallel_trees_merge_into_a_scene_that_holds_packed_images(bridge):
    packed_image("held", 0.4)
    with tempfile.TemporaryDirectory() as folder:
        tiled_image("held_tiles", [0.1, 0.5], folder, "held")
        reply = bridge.ok("grow_trees", trees=[TREE], workers=1)
        assert reply["workers"] == 1 and not reply["fallbacks"], reply
        assert reply["trees"][0]["built"] == "worker"
        assert bpy.data.images["held"].packed_file is not None and len(bpy.data.images["held_tiles"].packed_files) == 2


def test_the_parallel_woodland_builds_beside_packed_images(bridge):
    bridge.ok("add_primitive", type="plane", size=60.0, name="land")
    packed_image("atlas", 0.3)
    with tempfile.TemporaryDirectory() as folder:
        tiled_image("atlas_tiles", [0.3, 0.7], folder, "atlas")
        result = bridge.ok("woodland", ground=["land"], stands=STANDS, seed=2, **WOOD)
        assert result["growth"]["trees"]["workers"] == 1 and not result["growth"]["trees"]["fallbacks"], result["growth"]
        assert result["layers"]["trees"]["count"] > 0


run(globals())
