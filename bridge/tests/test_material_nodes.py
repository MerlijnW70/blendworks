import copy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import close, run
from texture_helpers import glb_parts, principled, world_state
from texture_stats import luminance

from blendworks_bridge.graph_catalog import BY_IDNAME, KINDS
from blendworks_bridge.limits import MAX_GRAPH_NODES

SIZE = 256
LIGHT = [0.5, 0.3, 0.12]
DARK = [0.1, 0.05, 0.02]
BANDS_SCALE = 8.0


def node(name, kind, inputs=None, settings=None, stops=None):
    spec = {"name": name, "type": kind}
    if inputs:
        spec["inputs"] = [{"socket": socket, **value} for socket, value in inputs.items()]
    if settings:
        spec["settings"] = [{"name": key, **value} for key, value in settings.items()]
    if stops:
        spec["stops"] = [{"position": position, "color": color} for position, color in stops]
    return spec


def link(source, source_socket, target, target_socket):
    return {"from_node": source, "from_socket": source_socket, "to_node": target, "to_socket": target_socket}


def wood_graph():
    nodes = [
        node("Coordinates", "texture_coordinate"),
        node("Rings", "wave_texture", {"Scale": {"number": BANDS_SCALE}, "Distortion": {"number": 0.0}, "Detail": {"number": 0.0}}, {"bands_direction": {"text": "X"}}),
        node("Tones", "color_ramp", stops=[(0.0, LIGHT), (1.0, DARK)]),
        node("Wood", "principled_bsdf", {"Roughness": {"number": 0.7}}),
        node("Output", "material_output"),
    ]
    links = [
        link("Coordinates", "Object", "Rings", "Vector"),
        link("Rings", "Fac", "Tones", "Fac"),
        link("Tones", "Color", "Wood", "Base Color"),
        link("Wood", "BSDF", "Output", "Surface"),
    ]
    return {"nodes": nodes, "links": links}


def plain_graph(extra_nodes=(), extra_links=()):
    nodes = [node("Shader", "principled_bsdf"), node("Output", "material_output"), *extra_nodes]
    return {"nodes": nodes, "links": [link("Shader", "BSDF", "Output", "Surface"), *extra_links]}


def sheet(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=0.5)
    bridge.ok("uv_smart_project", name="Sheet")


def srgb(value):
    return numpy.where(value <= 0.0031308, value * 12.92, 1.055 * numpy.power(value, 1 / 2.4) - 0.055)


def encoded_luminance(color):
    encoded = srgb(numpy.array(color))
    return float(0.2126 * encoded[0] + 0.7152 * encoded[1] + 0.0722 * encoded[2])


def bake_base_color(bridge, material, name="Sheet", size=SIZE):
    bridge.ok("assign_material", name=name, material=material)
    bridge.ok("bake", names=[name], channels=["base_color"], size=size, overwrite=True, samples={"base_color": 16}, prefix="Swatch", device="cpu", time_limit=600.0)
    return bpy.data.images["Swatch_base_color"]


def test_a_wood_graph_bakes_to_the_expected_colour_statistics(bridge):
    sheet(bridge)
    result = bridge.ok("material_nodes", name="Wood", **wood_graph())
    assert result == {"name": "Wood", "created": True, "nodes": 5, "links": 4}
    bake_base_color(bridge, "Wood")
    values = luminance("Swatch_base_color", SIZE)
    phase = numpy.linspace(0.0, 2.0 * math.pi, 4096, endpoint=False)
    factor = 0.5 + 0.5 * numpy.sin(phase)
    ramp = numpy.array(LIGHT)[None, :] * (1 - factor[:, None]) + numpy.array(DARK)[None, :] * factor[:, None]
    shades = 0.2126 * srgb(ramp[:, 0]) + 0.7152 * srgb(ramp[:, 1]) + 0.0722 * srgb(ramp[:, 2])
    assert abs(float(values.mean()) - float(shades.mean())) < 0.02, (values.mean(), shades.mean())
    assert abs(float(values.max()) - encoded_luminance(LIGHT)) < 0.03 and abs(float(values.min()) - encoded_luminance(DARK)) < 0.03
    assert abs(float(values.std()) - float(shades.std())) < 0.03, (values.std(), shades.std())
    explained = max(float(values.mean(axis=0).var()), float(values.mean(axis=1).var())) / float(values.var())
    assert explained >= 0.9, explained


def test_a_graph_reads_back_and_rebuilds_into_the_same_graph(bridge):
    bridge.ok("material_nodes", name="Wood", **wood_graph())
    first = bridge.ok("material_info", name="Wood")
    assert first["editable"] is True and first["displacement"] == "bump"
    assert [entry["name"] for entry in first["nodes"]] == ["Coordinates", "Rings", "Tones", "Wood", "Output"]
    rings = first["nodes"][1]
    assert rings["inputs"] == [{"socket": "Scale", "number": BANDS_SCALE}, {"socket": "Detail", "number": 0.0}]
    assert "settings" not in rings and first["nodes"][2]["stops"][0] == {"position": 0.0, "color": LIGHT + [1.0]}
    assert first["links"][0] == link("Coordinates", "Object", "Rings", "Vector")
    bridge.ok("material_nodes", name="Copy", nodes=first["nodes"], links=first["links"], displacement=first["displacement"])
    second = bridge.ok("material_info", name="Copy")
    assert {key: value for key, value in second.items() if key != "name"} == {key: value for key, value in first.items() if key != "name"}
    bridge.ok("material_nodes", name="Wood", nodes=second["nodes"], links=second["links"])
    assert bridge.ok("material_info", name="Wood")["nodes"] == first["nodes"]


def test_settings_stops_and_choice_inputs_survive_the_round_trip(bridge):
    nodes = [
        node("Noise", "noise_texture", {"Scale": {"number": 3.5}, "Vector": {"vector": [1.0, 2.0, 3.0]}}, {"noise_type": {"text": "RIDGED_MULTIFRACTAL"}, "normalize": {"boolean": False}}),
        node("Blend", "mix", {"A_Color": {"color": [0.1, 0.2, 0.3, 1.0]}}, {"data_type": {"text": "RGBA"}, "blend_type": {"text": "MULTIPLY"}}),
        node("Operation", "math", {"Value_001": {"number": 2.0}}, {"operation": {"text": "MULTIPLY"}, "use_clamp": {"boolean": True}}),
        node("Tones", "color_ramp", stops=[(0.0, [0, 0, 0]), (0.4, [1, 0, 0, 0.5]), (1.0, [1, 1, 1])]),
    ]
    links = [link("Noise", "Fac", "Operation", "Value"), link("Operation", "Value", "Tones", "Fac"), link("Tones", "Color", "Blend", "B_Color"), link("Blend", "Result_Color", "Shader", "Base Color")]
    graph = plain_graph(nodes, links)
    bridge.ok("material_nodes", name="Mixed", **graph)
    tree = bpy.data.materials["Mixed"].node_tree
    assert tree.nodes["Noise"].noise_type == "RIDGED_MULTIFRACTAL" and tree.nodes["Noise"].normalize is False
    assert tree.nodes["Blend"].data_type == "RGBA" and tree.nodes["Blend"].blend_type == "MULTIPLY"
    assert tree.nodes["Operation"].use_clamp is True and abs(tree.nodes["Tones"].color_ramp.elements[1].position - 0.4) < 1e-6
    close(list(tree.nodes["Noise"].inputs["Vector"].default_value), [1.0, 2.0, 3.0])
    info = bridge.ok("material_info", name="Mixed")
    by_name = {entry["name"]: entry for entry in info["nodes"]}
    assert {"name": "noise_type", "text": "RIDGED_MULTIFRACTAL"} in by_name["Noise"]["settings"]
    assert {"name": "normalize", "boolean": False} in by_name["Noise"]["settings"]
    assert {"socket": "A_Color", "color": [0.1, 0.2, 0.3, 1.0]} in by_name["Blend"]["inputs"]
    assert {"socket": "Value_001", "number": 2.0} in by_name["Operation"]["inputs"]
    assert [stop["position"] for stop in by_name["Tones"]["stops"]] == [0.0, 0.4, 1.0]
    bridge.ok("material_nodes", name="Again", nodes=info["nodes"], links=info["links"])
    assert bridge.ok("material_info", name="Again")["nodes"] == info["nodes"]


def test_a_procedural_preset_reads_back_and_rebuilds_to_the_same_look(bridge):
    sheet(bridge)
    bridge.ok("material_procedural", name="Preset", wood={"seed": 3, "scale": 4.0})
    info = bridge.ok("material_info", name="Preset")
    assert info["editable"] is True and len(info["nodes"]) > 8
    kinds = {entry["type"] for entry in info["nodes"]}
    assert {"principled_bsdf", "material_output", "wave_texture", "noise_texture", "mapping", "texture_coordinate", "displacement"} <= kinds
    bridge.ok("material_nodes", name="Rebuilt", nodes=info["nodes"], links=info["links"], displacement=info["displacement"])
    original = numpy.array(bake_base_color(bridge, "Preset", size=64).pixels[:])
    rebuilt = numpy.array(bake_base_color(bridge, "Rebuilt", size=64).pixels[:])
    assert float(numpy.abs(original - rebuilt).mean()) < 1e-3
    assert float(original.std()) > 0.02


def test_a_material_with_nodes_outside_the_list_says_so(bridge):
    bridge.ok("add_material", name="Plain", base_color=[0.2, 0.2, 0.2])
    material = bpy.data.materials["Plain"]
    material.node_tree.nodes.new("ShaderNodeTexImage")
    info = bridge.ok("material_info", name="Plain")
    assert info["editable"] is False and "nodes" not in info
    assert info["unsupported"] == [{"name": "Image Texture", "type": "ShaderNodeTexImage"}]
    bridge.refuse("material_info", "not_found", name="Missing")


def test_the_list_offers_the_documented_node_families_and_no_script_node(bridge):
    required = {
        "principled_bsdf", "noise_texture", "voronoi_texture", "wave_texture", "color_ramp", "mix", "math", "vector_math", "mapping",
        "texture_coordinate", "bump", "normal_map", "geometry", "ambient_occlusion", "emission", "mix_shader", "map_range", "separate_xyz",
    }
    assert required <= set(KINDS)
    assert len(KINDS) == len(BY_IDNAME)
    assert not [name for name, kind in KINDS.items() if "script" in name.lower() or "Script" in kind.idname or "Group" in kind.idname]
    for kind in KINDS.values():
        for setting in kind.settings:
            assert "script" not in setting.lower() and "filepath" not in setting.lower() and "bytecode" not in setting.lower()
    for name in ("script", "shader_script", "ShaderNodeScript", "group", "image_texture"):
        bridge.refuse("material_nodes", "bad_args", name="Bad", **plain_graph([node("Extra", name)]))
    assert "Bad" not in bpy.data.materials
    for material in bpy.data.materials:
        assert not any(item.bl_idname in ("ShaderNodeScript", "ShaderNodeGroup") for item in material.node_tree.nodes)


def refused(bridge, message_part, **graph):
    before = world_state()
    message = bridge.refuse("material_nodes", "bad_args", name="Wood", **graph)
    assert message_part in message, message
    assert world_state() == before
    assert "blendworks_check" not in [group.name for group in bpy.data.node_groups]


def test_invalid_graphs_are_refused_and_leave_the_scene_unchanged(bridge):
    bridge.ok("material_nodes", name="Wood", **wood_graph())
    good = wood_graph()

    unknown_socket = copy.deepcopy(good)
    unknown_socket["links"][1]["to_socket"] = "Strength"
    refused(bridge, "no socket Strength", **unknown_socket)

    unknown_setting = copy.deepcopy(good)
    unknown_setting["nodes"][1]["settings"] = [{"name": "script", "text": "x"}]
    refused(bridge, "no setting script", **unknown_setting)

    wrong_value = copy.deepcopy(good)
    wrong_value["nodes"][1]["inputs"] = [{"socket": "Scale", "vector": [1, 2, 3]}]
    refused(bridge, "give number", **wrong_value)

    bad_choice = copy.deepcopy(good)
    bad_choice["nodes"][1]["settings"] = [{"name": "bands_direction", "text": "W"}]
    refused(bridge, "must be one of", **bad_choice)

    shader_into_value = copy.deepcopy(good)
    shader_into_value["nodes"].append(node("Sum", "math"))
    shader_into_value["links"].append(link("Wood", "BSDF", "Sum", "Value"))
    refused(bridge, "cannot link the shader output", **shader_into_value)

    value_into_shader = copy.deepcopy(good)
    value_into_shader["links"][3] = link("Rings", "Fac", "Output", "Surface")
    refused(bridge, "cannot link the value output", **value_into_shader)

    twice = copy.deepcopy(good)
    twice["links"].append(link("Rings", "Fac", "Tones", "Fac"))
    refused(bridge, "already has a link", **twice)

    duplicate = copy.deepcopy(good)
    duplicate["nodes"].append(node("Rings", "math"))
    refused(bridge, "used twice", **duplicate)

    no_output = copy.deepcopy(good)
    no_output["nodes"] = no_output["nodes"][:-1]
    no_output["links"] = no_output["links"][:-1]
    refused(bridge, "exactly one material_output", **no_output)

    unlinked = copy.deepcopy(good)
    unlinked["links"] = unlinked["links"][:-1]
    refused(bridge, "Surface", **unlinked)

    unknown_node = copy.deepcopy(good)
    unknown_node["links"][0]["from_node"] = "Nowhere"
    refused(bridge, "no node named Nowhere", **unknown_node)

    stops_elsewhere = copy.deepcopy(good)
    stops_elsewhere["nodes"][1]["stops"] = [{"position": 0.0, "color": [0, 0, 0]}, {"position": 1.0, "color": [1, 1, 1]}]
    refused(bridge, "only a color_ramp has stops", **stops_elsewhere)

    unordered = copy.deepcopy(good)
    unordered["nodes"][2]["stops"] = [{"position": 0.6, "color": [0, 0, 0]}, {"position": 0.2, "color": [1, 1, 1]}]
    refused(bridge, "rise strictly", **unordered)

    disabled = copy.deepcopy(good)
    disabled["nodes"].append(node("Blend", "mix"))
    disabled["links"].append(link("Tones", "Color", "Blend", "A_Color"))
    refused(bridge, "no socket A_Color", **disabled)

    assert bridge.ok("material_info", name="Wood")["nodes"][1]["name"] == "Rings"


def test_cycles_and_self_links_are_refused(bridge):
    bridge.ok("material_nodes", name="Wood", **wood_graph())
    loop = plain_graph([node("A", "math"), node("B", "math")], [link("A", "Value", "B", "Value"), link("B", "Value", "A", "Value")])
    refused(bridge, "cycle through A, B", **loop)
    selfish = plain_graph([node("A", "math")], [link("A", "Value", "A", "Value_001")])
    refused(bridge, "cycle through A", **selfish)
    long = plain_graph(
        [node(f"M{index}", "math") for index in range(4)],
        [link(f"M{index}", "Value", f"M{(index + 1) % 4}", "Value") for index in range(4)],
    )
    refused(bridge, "cycle", **long)


def test_graphs_over_the_caps_are_refused(bridge):
    bridge.ok("material_nodes", name="Wood", **wood_graph())
    too_many = plain_graph([node(f"V{index}", "value") for index in range(MAX_GRAPH_NODES - 1)])
    assert len(too_many["nodes"]) == MAX_GRAPH_NODES + 1
    refused(bridge, "at most", **too_many)
    exactly = plain_graph([node(f"V{index}", "value") for index in range(MAX_GRAPH_NODES - 2)])
    assert bridge.ok("material_nodes", name="Cap", **exactly)["nodes"] == MAX_GRAPH_NODES
    chain = [node(f"C{index}", "math") for index in range(60)]
    many_links = [link(f"C{index % 60}", "Value", f"C{(index + 1) % 60}", "Value") for index in range(301)]
    refused(bridge, "at most", **plain_graph(chain, many_links))
    bridge.refuse("material_nodes", "bad_args", name="Empty", nodes=[])


def test_the_graph_works_with_layers_bake_and_gltf_export(bridge):
    sheet(bridge)
    bridge.ok("material_nodes", name="Wood", **wood_graph())
    bridge.ok("assign_material", name="Sheet", material="Wood")
    layered = bridge.ok("material_layer", material="Wood", rust={"coverage": 0.6}, mask="noise", amount=0.5)
    assert layered["nodes"] > 5
    baked = bridge.ok("bake", names=["Sheet"], channels=["base_color", "roughness"], size=64, rewire=True, samples={"base_color": 1, "roughness": 1}, prefix="Wood", device="cpu", time_limit=600.0)
    assert baked["materials"] == ["Wood_baked"]
    exported = bridge.ok("export", path="wood.glb")
    document, _ = glb_parts(os.path.join(bridge.workspace, "wood.glb"))
    material = document["materials"][0]["pbrMetallicRoughness"]
    assert "baseColorTexture" in material and "metallicRoughnessTexture" in material
    assert exported["objects"] == ["Sheet"]


def test_constant_values_export_as_gltf_factors(bridge):
    bridge.ok("add_primitive", type="cube", name="Cube", size=0.2)
    graph = plain_graph()
    graph["nodes"][0] = node("Shader", "principled_bsdf", {"Base Color": {"color": [0.2, 0.4, 0.6, 1.0]}, "Metallic": {"number": 0.5}, "Roughness": {"number": 0.3}})
    bridge.ok("material_nodes", name="Paint", **graph)
    close(list(bpy.data.materials["Paint"].diffuse_color), [0.2, 0.4, 0.6, 1.0])
    bridge.ok("assign_material", name="Cube", material="Paint")
    bridge.ok("export", path="paint.glb")
    document, _ = glb_parts(os.path.join(bridge.workspace, "paint.glb"))
    material = document["materials"][0]["pbrMetallicRoughness"]
    close(material["baseColorFactor"], [0.2, 0.4, 0.6, 1.0], 1e-4)
    close([material["metallicFactor"], material["roughnessFactor"]], [0.5, 0.3], 1e-4)


def test_displacement_and_viewport_colour_follow_the_graph(bridge):
    graph = plain_graph()
    graph["nodes"][0] = node("Shader", "principled_bsdf", {"Base Color": {"color": [0.5, 0.25, 0.125]}})
    result = bridge.ok("material_nodes", name="Shown", displacement="both", **graph)
    assert result["created"] is True
    material = bpy.data.materials["Shown"]
    assert material.displacement_method == "BOTH"
    close(list(material.diffuse_color), [0.5, 0.25, 0.125, 1.0])
    assert principled(material).inputs["Base Color"].default_value[0] == 0.5
    assert bridge.ok("material_nodes", name="Shown", **graph)["created"] is False
    assert bridge.ok("material_info", name="Shown")["displacement"] == "bump"
    bridge.refuse("material_nodes", "bad_args", name="Shown", displacement="none", **graph)


run(globals())
