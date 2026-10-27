import base64
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from texture_helpers import glb_parts

OUTPUT = os.path.join(tempfile.gettempdir(), "blendworks-textured-prop")
BAKE_SIZE = 1024
CHANNELS = ["base_color", "roughness", "metallic", "normal", "ao"]


def box(bridge, name, size, location, bevel):
    bridge.ok("add_primitive", type="cube", name=name, size=1.0, location=location)
    bridge.ok("transform", name=name, scale=size)
    bridge.ok("apply_transform", name=name)
    bridge.ok("bevel", name=name, width=bevel, segments=3)


def rivet(bridge, name, location):
    bridge.ok("add_primitive", type="sphere", name=name, radius=0.011, segments=12, rings=8, location=location)
    bridge.ok("transform", name=name, scale=[1.0, 1.0, 0.45])
    bridge.ok("apply_transform", name=name)


def build_prop(bridge):
    box(bridge, "Plank", [1.2, 0.24, 0.05], [0.0, 0.0, 0.025], 0.006)
    bridge.ok("material_procedural", name="Oak", wood={"grain": "x", "seed": 3})
    bridge.ok("material_layer", material="Oak", dirt={"seed": 5}, mask="cavity", amount=0.5, distance=0.03, mask_scale=40.0)
    bridge.ok("material_layer", material="Oak", wood={"light_color": [0.42, 0.28, 0.15], "dark_color": [0.3, 0.19, 0.1], "grain": "x", "bump": 0.0}, mask="edges", amount=0.4, distance=0.006, breakup=0.6, mask_scale=60.0)
    bridge.ok("material_procedural", name="Iron", worn_metal={"color": [0.2, 0.2, 0.21], "roughness": 0.5, "wear": 0.6, "scratch_direction": "y"})
    bridge.ok("material_layer", material="Iron", rust={"coverage": 0.8, "seed": 2}, mask="noise", amount=0.35, mask_scale=14.0)
    bridge.ok("material_layer", material="Iron", worn_metal={"color": [0.62, 0.61, 0.6], "roughness": 0.25, "wear": 0.2}, mask="edges", amount=0.4, distance=0.004, mask_scale=80.0)
    bridge.ok("assign_material", name="Plank", material="Oak")
    parts = ["Plank"]
    for index, x in enumerate((-0.42, 0.42)):
        band = f"Band{index}"
        box(bridge, band, [0.06, 0.252, 0.062], [x, 0.0, 0.025], 0.004)
        bridge.ok("assign_material", name=band, material="Iron")
        parts.append(band)
        for side, y in enumerate((-0.07, 0.07)):
            name = f"Rivet{index}{side}"
            rivet(bridge, name, [x, y, 0.0565])
            bridge.ok("assign_material", name=name, material="Iron")
            parts.append(name)
    bridge.ok("join", names=parts)
    bridge.ok("uv_smart_project", name="Plank", angle_limit=60.0, island_margin=0.004)
    return "Plank"


def save_preview(result, path):
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(result["images"][0]["data"]))


def test_textured_prop_from_presets(bridge):
    shutil.rmtree(OUTPUT, ignore_errors=True)
    os.makedirs(OUTPUT)
    name = build_prop(bridge)
    save_preview(bridge.ok("render_preview", views=["three-quarter"], resolution=768, samples=24), os.path.join(OUTPUT, "procedural.png"))
    baked = bridge.ok("bake", names=[name], channels=CHANNELS, size=BAKE_SIZE, prefix="Prop", rewire=True, samples={"ao": 32}, time_limit=300.0)
    assert baked["material"] == "Prop_baked" and baked["images"] == [f"Prop_{channel}" for channel in CHANNELS]
    for channel in CHANNELS:
        image = bpy.data.images[f"Prop_{channel}"]
        assert tuple(image.size) == (BAKE_SIZE, BAKE_SIZE)
        bridge.ok("image_save", name=image.name, path=f"textures/{image.name}.png")
    exported = bridge.ok("export", path="plank.glb")
    document = glb_parts(os.path.join(bridge.workspace, "plank.glb"))[0]
    material = document["materials"][0]
    assert {"baseColorTexture", "metallicRoughnessTexture"} <= set(material["pbrMetallicRoughness"])
    assert {"normalTexture", "occlusionTexture"} <= set(material)
    assert len(document["images"]) >= 3
    bridge.ok("new_scene")
    bridge.ok("import", path="plank.glb")
    preview = bridge.ok("render_preview", views=["three-quarter", "top"], resolution=1024, samples=32)
    save_preview(preview, os.path.join(OUTPUT, "preview.png"))
    save_preview({"images": preview["images"][1:]}, os.path.join(OUTPUT, "preview-top.png"))
    shutil.copy(os.path.join(bridge.workspace, "plank.glb"), os.path.join(OUTPUT, "plank.glb"))
    report = {"device": baked["device"], "device_label": baked["device_label"], "channels": baked["channels"], "seconds": baked["seconds"], "glb_bytes": exported["bytes"]}
    with open(os.path.join(OUTPUT, "bake.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    assert os.path.getsize(os.path.join(OUTPUT, "preview.png")) > 10_000
    print(f"textured prop: preview {os.path.join(OUTPUT, 'preview.png')}, bake on {baked['device_label']} in {baked['seconds']} s")


if __name__ == "__main__":
    run(globals())
