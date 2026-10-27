import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import close, run
from texture_helpers import glb_image_bytes, glb_parts, graph_signature, linked_from, principled, upstream_image, world_state, write_image

from blendworks_bridge.commands import pbr as pbr_command

MAPS = {
    "base_color": ("base.png", (0.8, 0.4, 0.2, 1.0)),
    "metallic": ("metal.png", (1.0, 1.0, 1.0, 1.0)),
    "roughness": ("rough.png", (0.4, 0.4, 0.4, 1.0)),
    "normal": ("normal.png", (0.5, 0.5, 1.0, 1.0)),
    "height": ("height.png", (0.5, 0.5, 0.5, 1.0)),
    "emission": ("glow.png", (1.0, 0.8, 0.1, 1.0)),
    "alpha": ("alpha.png", (0.9, 0.9, 0.9, 1.0)),
    "ao": ("ao.png", (0.7, 0.7, 0.7, 1.0)),
}
COLOR_MAPS = ("base_color", "emission")


def write_maps(folder):
    for name, rgba in MAPS.values():
        write_image(folder, f"maps/{name}", 16, 16, rgba)
    return {f"{key}_path": f"maps/{name}" for key, (name, _) in MAPS.items()}


def test_material_pbr_round_trip_keeps_every_map(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    paths = write_maps(bridge.workspace)
    result = bridge.ok("material_pbr", name="Painted", normal_strength=0.8, emission_strength=3.0, scale=[2.0, 2.0], **paths)
    assert result["created"] is True and set(result["maps"]) == set(MAPS)
    for key, image_name in result["maps"].items():
        expected = "sRGB" if key in COLOR_MAPS else "Non-Color"
        assert bpy.data.images[image_name].colorspace_settings.name == expected, (key, image_name)
        assert result["colorspaces"][image_name] == expected
    material = bpy.data.materials["Painted"]
    assert material.displacement_method == "BUMP"
    assert any("height" in note for note in result["warnings"])
    bridge.ok("assign_material", name="Box", material="Painted")
    bridge.ok("export", path="painted.glb")
    document, binary = glb_parts(os.path.join(bridge.workspace, "painted.glb"))
    exported = document["materials"][0]
    pbr = exported["pbrMetallicRoughness"]
    for texture in (pbr["baseColorTexture"], pbr["metallicRoughnessTexture"], exported["normalTexture"], exported["emissiveTexture"], exported["occlusionTexture"]):
        assert "KHR_texture_transform" in texture.get("extensions", {}), texture
        close(texture["extensions"]["KHR_texture_transform"]["scale"], [2.0, 2.0])
    close(exported["normalTexture"]["scale"], 0.8)
    close(exported["extensions"]["KHR_materials_emissive_strength"]["emissiveStrength"], 3.0)
    assert exported["alphaMode"] == "BLEND"
    normal_bytes, mime = glb_image_bytes(document, binary, exported["normalTexture"])
    with open(os.path.join(bridge.workspace, "maps", "normal.png"), "rb") as handle:
        assert mime == "image/png" and normal_bytes == handle.read()
    bridge.ok("new_scene")
    imported = bridge.ok("import", path="painted.glb")["objects"]
    material = bpy.data.objects[imported[0]].material_slots[0].material
    shader = principled(material)
    assert upstream_image(shader.inputs["Base Color"]).colorspace_settings.name == "sRGB"
    assert upstream_image(shader.inputs["Emission Color"]).colorspace_settings.name == "sRGB"
    for socket in ("Metallic", "Roughness", "Normal"):
        assert upstream_image(shader.inputs[socket]).colorspace_settings.name == "Non-Color", socket
    node, _ = linked_from(shader.inputs["Normal"])
    assert node.type == "NORMAL_MAP"


def test_material_pbr_orm_channels_follow_the_order(bridge):
    write_image(bridge.workspace, "orm.png", 8, 8, (0.2, 0.6, 0.9, 1.0))
    bridge.ok("material_pbr", name="Packed", orm_path="orm.png")
    shader = principled(bpy.data.materials["Packed"])
    assert linked_from(shader.inputs["Roughness"])[1].name == "Green"
    assert linked_from(shader.inputs["Metallic"])[1].name == "Blue"
    bridge.ok("material_pbr", name="Swapped", orm="orm.png", orm_order="rmo")
    material = bpy.data.materials["Swapped"]
    shader = principled(material)
    assert linked_from(shader.inputs["Roughness"])[1].name == "Red"
    assert linked_from(shader.inputs["Metallic"])[1].name == "Green"
    group = next(node for node in material.node_tree.nodes if node.type == "GROUP")
    assert group.node_tree.name.startswith("glTF Material Output")
    assert linked_from(group.inputs["Occlusion"])[1].name == "Blue"
    assert bpy.data.images["orm.png"].colorspace_settings.name == "Non-Color"
    bridge.ok("add_primitive", type="cube", name="Box")
    bridge.ok("assign_material", name="Box", material="Swapped")
    bridge.ok("export", path="packed.glb")
    exported = glb_parts(os.path.join(bridge.workspace, "packed.glb"))[0]["materials"][0]
    assert "metallicRoughnessTexture" in exported["pbrMetallicRoughness"] and "occlusionTexture" in exported


def test_material_pbr_flips_directx_normals(bridge):
    write_image(bridge.workspace, "dx.png", 4, 4, (0.5, 0.25, 1.0, 1.0))
    result = bridge.ok("material_pbr", name="Dx", normal_path="dx.png", normal_convention="directx")
    flipped = bpy.data.images[result["maps"]["normal"]]
    assert flipped.name == "dx.png_opengl" and flipped.colorspace_settings.name == "Non-Color"
    close(list(flipped.pixels[:3]), [128 / 255, 191 / 255, 1.0], 1.5 / 255)
    shader = principled(bpy.data.materials["Dx"])
    assert upstream_image(shader.inputs["Normal"]) == flipped


def test_material_pbr_uv_map_and_mapping(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet")
    write_image(bridge.workspace, "base.png", 4, 4, (1.0, 0.0, 0.0, 1.0))
    bridge.ok("material_pbr", name="Tiled", base_color_path="base.png", uv_map="UVMap", offset=[0.25, 0.5], rotation=90.0)
    nodes = {node.type: node for node in bpy.data.materials["Tiled"].node_tree.nodes}
    assert nodes["UVMAP"].uv_map == "UVMap"
    close(list(nodes["MAPPING"].inputs["Location"].default_value), [0.25, 0.5, 0.0])
    close(nodes["MAPPING"].inputs["Rotation"].default_value[2], 1.5707963, 1e-5)
    bridge.ok("assign_material", name="Sheet", material="Tiled")
    before = world_state()
    bridge.refuse("material_pbr", "bad_args", name="Tiled", base_color_path="base.png", uv_map="Missing")
    assert world_state() == before


def test_material_pbr_refusals_leave_the_scene(bridge):
    write_image(bridge.workspace, "base.png", 4, 4, (1.0, 0.0, 0.0, 1.0))
    write_image(bridge.workspace, "rough.png", 4, 4, (0.5, 0.5, 0.5, 1.0))
    bridge.ok("add_material", name="Existing", roughness=0.3)
    bridge.ok("image_load", path="base.png", name="Base")
    outside = os.path.join(os.path.dirname(bridge.workspace), "outside.png")
    write_image(os.path.dirname(bridge.workspace), "outside.png", 4, 4, (1.0, 1.0, 1.0, 1.0))
    before = world_state()
    assert "specular_path" in bridge.refuse("material_pbr", "bad_args", name="Existing", specular_path="base.png")
    bridge.refuse("material_pbr", "bad_args", name="Existing", base_color="Base", base_color_path="base.png")
    bridge.refuse("material_pbr", "forbidden", name="Existing", base_color_path="../outside.png")
    bridge.refuse("material_pbr", "forbidden", name="Existing", roughness_path=outside)
    bridge.refuse("material_pbr", "not_found", name="Existing", base_color="Ghost")
    bridge.refuse("material_pbr", "bad_args", name="Existing", orm_path="rough.png", roughness_path="rough.png")
    assert "one colour space" in bridge.refuse("material_pbr", "bad_args", name="Existing", base_color="Base", roughness="Base")
    bridge.refuse("material_pbr", "bad_args", name="Existing")
    bridge.refuse("material_pbr", "bad_args", name="Existing", base_color="Base", orm_order="xyz")
    assert world_state() == before
    os.remove(outside)


def test_material_pbr_failure_restores_material_and_colour_spaces(bridge):
    write_image(bridge.workspace, "rough.png", 4, 4, (0.5, 0.5, 0.5, 1.0))
    bridge.ok("image_load", path="rough.png", name="Rough", colorspace="srgb")
    bridge.ok("add_material", name="Existing", roughness=0.3)
    before = world_state()
    signature = graph_signature(bpy.data.materials["Existing"])
    original = pbr_command.build_pbr

    def broken(material, maps, options):
        original(material, maps, options)
        raise RuntimeError("injected failure after wiring")

    pbr_command.build_pbr = broken
    try:
        assert "injected" in bridge.refuse("material_pbr", "failed", name="Existing", roughness="Rough")
    finally:
        pbr_command.build_pbr = original
    assert graph_signature(bpy.data.materials["Existing"]) == signature
    assert bpy.data.images["Rough"].colorspace_settings.name == "sRGB"
    assert world_state() == before
    result = bridge.ok("material_pbr", name="Existing", roughness="Rough")
    assert result["created"] is False and bpy.data.images["Rough"].colorspace_settings.name == "Non-Color"


if __name__ == "__main__":
    run(globals())
