import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run, snapshot
from texture_helpers import write_image

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_header_only(path, width, height):
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(header)) + b"IHDR" + header + struct.pack(">I", zlib.crc32(b"IHDR" + header))
    with open(path, "wb") as handle:
        handle.write(PNG_SIGNATURE + chunk)


def png_depth(path):
    with open(path, "rb") as handle:
        header = handle.read(26)
    assert header.startswith(PNG_SIGNATURE), path
    return header[24], header[25]


def state():
    return snapshot(), sorted(image.name for image in bpy.data.images)


def test_image_load_reads_every_format(bridge):
    for extension, float_buffer in ((".png", False), (".jpg", False), (".exr", True), (".webp", False)):
        write_image(bridge.workspace, f"swatch{extension}", 8, 4, (0.5, 0.25, 0.1, 1.0), float_buffer)
        result = bridge.ok("image_load", path=f"swatch{extension}", name=f"Swatch{extension}")
        assert result["name"] == f"Swatch{extension}"
        assert result["size"] == [8, 4], result
        assert result["source"] == "file" and result["packed"] is False
        assert result["file"] == f"swatch{extension}"
        assert result["float"] is (extension == ".exr")
        assert result["colorspace"] == ("linear" if extension == ".exr" else "srgb"), result
        assert result["channels"] in (3, 4)
        assert result["users"] == 0


def test_image_load_sets_name_and_colour_space(bridge):
    write_image(bridge.workspace, "maps/rough.png", 4, 4, (0.3, 0.3, 0.3, 1.0))
    result = bridge.ok("image_load", path="maps/rough.png", colorspace="non_color")
    assert result["name"] == "rough.png" and result["colorspace"] == "non_color"
    assert bpy.data.images["rough.png"].colorspace_settings.name == "Non-Color"
    assert bpy.data.images["rough.png"].use_fake_user is True


def test_image_load_refuses_bad_paths_and_sizes(bridge):
    write_image(bridge.workspace, "ok.png", 4, 4, (1.0, 1.0, 1.0, 1.0))
    bridge.ok("image_load", path="ok.png", name="Taken")
    png_header_only(os.path.join(bridge.workspace, "huge.png"), 9000, 16)
    with open(os.path.join(bridge.workspace, "junk.png"), "wb") as handle:
        handle.write(b"not an image at all")
    with open(os.path.join(bridge.workspace, "notes.txt"), "w") as handle:
        handle.write("text")
    outside = os.path.join(os.path.dirname(bridge.workspace), "outside.png")
    before = state()
    assert "outside" in bridge.refuse("image_load", "forbidden", path="../outside.png")
    bridge.refuse("image_load", "forbidden", path=outside)
    bridge.refuse("image_load", "forbidden", path="notes.txt")
    bridge.refuse("image_load", "not_found", path="missing.png")
    assert "8192" in bridge.refuse("image_load", "bad_args", path="huge.png")
    bridge.refuse("image_load", "bad_args", path="junk.png")
    bridge.refuse("image_load", "bad_args", path="ok.png", name="Taken")
    bridge.refuse("image_load", "bad_args", path="ok.png", colorspace="rec2020")
    assert state() == before


def test_image_new_makes_bake_targets(bridge):
    result = bridge.ok("image_new", name="Target", width=64, height=32)
    assert result["size"] == [64, 32] and result["float"] is False and result["colorspace"] == "srgb"
    assert result["source"] == "generated" and result["alpha"] is True
    result = bridge.ok("image_new", name="Data", width=16, height=16, float=True, alpha=False, colorspace="non_color", color=[0.25, 0.5, 0.75])
    assert result["float"] is True and result["colorspace"] == "non_color" and result["alpha"] is False, result
    close(bpy.data.images["Data"].pixels[:3], [0.25, 0.5, 0.75], 1e-6)
    assert bridge.ok("image_new", name="Linear", width=8, height=8, float=True)["colorspace"] == "linear"


def test_image_new_refuses_oversize_and_duplicates(bridge):
    bridge.ok("image_new", name="Target", width=8, height=8)
    before = state()
    bridge.refuse("image_new", "bad_args", name="Big", width=9000, height=8)
    bridge.refuse("image_new", "bad_args", name="Target", width=8, height=8)
    bridge.refuse("image_new", "bad_args", name="Odd", width=8, height=8, depth=8)
    assert state() == before


def test_image_info_lists_images(bridge):
    bridge.ok("image_new", name="B", width=4, height=4)
    write_image(bridge.workspace, "a.png", 2, 2, (1.0, 0.0, 0.0, 1.0))
    bridge.ok("image_load", path="a.png", name="A")
    listed = bridge.ok("image_info")["images"]
    assert [entry["name"] for entry in listed] == ["A", "B"], listed
    assert listed[0]["file"] == "a.png" and listed[1]["file"] is None
    only = bridge.ok("image_info", names=["B"])["images"]
    assert len(only) == 1 and only[0]["size"] == [4, 4]
    bridge.refuse("image_info", "not_found", names=["Ghost"])
    bridge.refuse("image_info", "bad_args", names=["B", "B"])


def reload_raw(path):
    image = bpy.data.images.load(path, check_existing=False)
    image.colorspace_settings.name = "Non-Color"
    pixels = list(image.pixels[:4])
    bpy.data.images.remove(image)
    return pixels


def test_image_save_encodes_colour_and_keeps_data_raw(bridge):
    bridge.ok("image_new", name="Linear", width=4, height=4, float=True, alpha=False)
    bpy.data.images["Linear"].pixels.foreach_set([0.5, 0.25, 0.1, 1.0] * 16)
    result = bridge.ok("image_save", name="Linear", path="out/linear.png", relink=False)
    assert result["path"] == "out/linear.png" and result["format"] == "png" and result["depth"] == 8
    path = os.path.join(bridge.workspace, "out", "linear.png")
    close(reload_raw(path)[:3], [188 / 255, 137 / 255, 89 / 255], 1.5 / 255)
    assert png_depth(path) == (8, 2)
    bridge.ok("image_new", name="Data", width=4, height=4, float=True, alpha=False, colorspace="non_color")
    bpy.data.images["Data"].pixels.foreach_set([0.5, 0.25, 0.1, 1.0] * 16)
    bridge.ok("image_save", name="Data", path="data16.png", depth=16, relink=False)
    path = os.path.join(bridge.workspace, "data16.png")
    close(reload_raw(path)[:3], [0.5, 0.25, 0.1], 1.0 / 65535 + 1e-6)
    assert png_depth(path) == (16, 2)
    bridge.ok("image_new", name="Byte", width=4, height=4, alpha=False)
    bpy.data.images["Byte"].pixels.foreach_set([128 / 255, 64 / 255, 32 / 255, 1.0] * 16)
    bridge.ok("image_save", name="Byte", path="byte.jpg", quality=100, relink=False)
    close(reload_raw(os.path.join(bridge.workspace, "byte.jpg"))[:3], [128 / 255, 64 / 255, 32 / 255], 3.0 / 255)
    assert bpy.data.images["Byte"].source == "GENERATED"


def test_image_save_relinks_to_the_file(bridge):
    bridge.ok("image_new", name="Baked", width=4, height=4, float=True, alpha=False)
    bpy.data.images["Baked"].pixels.foreach_set([0.5, 0.5, 0.5, 1.0] * 16)
    result = bridge.ok("image_save", name="Baked", path="baked.png")
    assert result["source"] == "file" and result["file"] == "baked.png"
    assert result["colorspace"] == "srgb" and result["float"] is False
    close(bpy.data.images["Baked"].pixels[:3], [188 / 255] * 3, 1.5 / 255)
    bridge.ok("image_new", name="Rough", width=4, height=4, colorspace="non_color")
    assert bridge.ok("image_save", name="Rough", path="rough.png")["colorspace"] == "non_color"


def test_image_save_refusals_leave_everything(bridge):
    bridge.ok("image_new", name="Img", width=4, height=4)
    before = state()
    bridge.refuse("image_save", "not_found", name="Ghost", path="a.png")
    bridge.refuse("image_save", "bad_args", name="Img", path="a.tga")
    bridge.refuse("image_save", "bad_args", name="Img", path="a.jpg", depth=16)
    bridge.refuse("image_save", "bad_args", name="Img", path="a.png", depth=12)
    bridge.refuse("image_save", "forbidden", name="Img", path="../escape.png")
    bridge.refuse("image_save", "bad_args", name="Img", path="a.png", quality=0)
    assert state() == before
    assert not os.path.exists(os.path.join(os.path.dirname(bridge.workspace), "escape.png"))
    assert os.listdir(bridge.workspace) == []


if __name__ == "__main__":
    run(globals())
