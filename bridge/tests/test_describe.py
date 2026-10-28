import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import Bridge, run

from blendworks_bridge.registry import COMMANDS

DESIGN_COMMANDS = {
    "describe", "scene_info", "new_scene", "select", "delete",
    "add_primitive", "transform", "apply_transform", "set_origin", "duplicate", "join", "rename", "parent",
    "extrude", "inset", "bevel", "subdivide", "decimate", "boolean", "mirror", "array", "solidify",
    "shade_smooth", "shade_flat", "recalc_normals", "merge_by_distance", "apply_modifier",
    "mesh_from_data", "curve_from_points", "text_object",
    "lathe", "sweep", "loft", "extrude_outline", "gear", "sprocket", "roller_chain",
    "instances", "rivet_line", "generate_lods", "add_modifier", "mesh_query", "transform_selection", "displace_noise", "noise_displace", "heightfield", "scatter", "erode",
    "add_material", "assign_material", "vertex_colors",
    "uv_smart_project", "uv_unwrap", "uv_info", "uv_pack",
    "image_load", "image_new", "image_save", "image_info",
    "material_pbr", "material_procedural", "material_layer", "bake",
    "add_light", "add_camera", "look_at", "set_world",
    "render_preview", "export", "save_blend", "import",
    "load_blend", "checkpoint", "restore_checkpoint",
    "clean_mesh", "engrave", "engrave_scale",
    "material_nodes", "material_info", "add_empty", "collection_create", "collection_link", "collection_unlink",
}
ASSET_LIBRARY_COMMANDS = {"set_world_hdri"}
SLOW = {"slow": True, "timeout": 300, "max_timeout": 1800}
DECLARED_METADATA = {
    "bake": {"slow": True, "timeout": 660, "max_timeout": 1200},
    "boolean": dict(SLOW, destructive=True, destructive_when="cutter_action is delete"),
    "image_save": {"writes_files": True, "destructive": True, "destructive_when": "the file already exists", "slow": False},
    **{name: SLOW for name in ("decimate", "import", "uv_pack", "set_world_hdri", "apply_modifier", "sweep", "loft", "instances",
                               "rivet_line", "roller_chain", "displace_noise", "noise_displace", "heightfield", "scatter", "erode", "mesh_from_data", "generate_lods", "clean_mesh", "engrave")},
}
SCHEMA_KEYS = {"type", "description", "properties", "required", "additionalProperties", "items", "enum", "minimum",
               "maximum", "exclusiveMinimum", "minItems", "maxItems", "minLength", "maxLength", "default"}


def walk(schema):
    yield schema
    for child in schema.get("properties", {}).values():
        yield from walk(child)
    if "items" in schema:
        yield from walk(schema["items"])


def test_describe_matches_the_registry(bridge):
    described = {entry["name"]: entry for entry in bridge.ok("describe")["commands"]}
    registry = bridge.handler.registry
    assert sorted(described) == registry.names()
    for name, entry in described.items():
        command = registry.get(name)
        assert entry["schema"] == command.schema, name
        assert entry["description"] == command.description, name
        assert entry.get("dangerous", False) == command.dangerous, name
        assert entry["mutates"] == command.mutates and entry["slow"] == command.slow, name
        assert 0 < entry["timeout"] <= entry["max_timeout"], name
    python = Bridge(bridge.workspace, allow_python=True)
    assert sorted(entry["name"] for entry in python.ok("describe")["commands"]) == sorted(COMMANDS)


def test_every_design_command_exists(bridge):
    names = set(bridge.handler.registry.names())
    assert DESIGN_COMMANDS <= names, sorted(DESIGN_COMMANDS - names)
    assert ASSET_LIBRARY_COMMANDS <= names, sorted(ASSET_LIBRARY_COMMANDS - names)
    assert set(COMMANDS) - DESIGN_COMMANDS - ASSET_LIBRARY_COMMANDS == {"run_python", "recover"}


def test_descriptions_are_one_line_and_schemas_are_closed(bridge):
    for entry in bridge.ok("describe")["commands"]:
        description = entry["description"]
        assert description and "\n" not in description and len(description) <= 200, entry["name"]
        schema = entry["schema"]
        assert schema["type"] == "object" and schema["additionalProperties"] is False, entry["name"]
        assert set(schema["required"]) <= set(schema["properties"]), entry["name"]
        for node in walk(schema):
            assert set(node) <= SCHEMA_KEYS, (entry["name"], set(node) - SCHEMA_KEYS)
        for field, node in schema["properties"].items():
            assert node.get("description"), (entry["name"], field)


def test_metadata_marks_mutation_destruction_and_time(bridge):
    described = {entry["name"]: entry for entry in bridge.ok("describe")["commands"]}
    read_only = {name for name, entry in described.items() if not entry["mutates"] and not entry["writes_files"]}
    assert {"describe", "scene_info", "render_preview", "image_info", "uv_info"} <= read_only
    assert not read_only & {"add_primitive", "delete", "export", "save_blend", "checkpoint", "load_blend"}
    destructive = {name for name, entry in described.items() if entry["destructive"]}
    assert {"delete", "new_scene", "export", "boolean", "save_blend", "image_save", "load_blend", "restore_checkpoint", "checkpoint"} <= destructive
    assert not destructive & {"add_primitive", "scene_info", "render_preview", "transform", "select"}
    assert described["boolean"]["destructive_when"] == "cutter_action is delete"
    assert described["export"]["destructive_when"] == "the file already exists"
    slow = {name for name, entry in described.items() if entry["slow"]}
    assert {"bake", "boolean", "export", "render_preview", "import", "save_blend", "load_blend"} <= slow
    assert all(described[name]["timeout"] >= 300 for name in slow)
    assert described["add_primitive"]["timeout"] == 120 and described["add_primitive"]["max_timeout"] == 600
    assert described["bake"]["timeout"] == 660
    assert {name for name, entry in described.items() if entry.get("internal")} == {"describe", "recover"}
    python = Bridge(bridge.workspace, allow_python=True).ok("describe")["commands"]
    run_python = next(entry for entry in python if entry["name"] == "run_python")
    assert run_python["slow"] and run_python["destructive"] and run_python["mutates"] and run_python["timeout"] == 300


def test_metadata_lives_with_each_command_declaration(bridge):
    described = {entry["name"]: entry for entry in bridge.ok("describe")["commands"]}
    for name, expected in DECLARED_METADATA.items():
        for key, value in expected.items():
            assert described[name].get(key) == value, (name, key, described[name].get(key), value)
    slow_defaults = {(entry["timeout"], entry["max_timeout"]) for entry in described.values() if entry["slow"]}
    assert (300, 1800) in slow_defaults


def test_no_override_table_remains_in_the_policy(bridge):
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blendworks_bridge")
    with open(os.path.join(folder, "policy.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert isinstance(node.value, ast.Constant), (node.targets[0].id, "only constants may be assigned at module level")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in COMMANDS, f"policy.py names the command {node.value}"
        assert not (isinstance(node, ast.Name) and "OVERRIDE" in node.id.upper()), node.id


def test_every_command_refuses_unknown_fields(bridge):
    for name in bridge.handler.registry.names():
        message = bridge.refuse(name, "bad_args", unexpected_field=1)
        assert "unexpected_field" in message, (name, message)


def test_every_command_is_tested_on_success_and_refusal(bridge):
    tested = {"ok": set(), "refuse": set()}
    folder = os.path.dirname(os.path.abspath(__file__))
    for file_name in os.listdir(folder):
        if not (file_name.startswith("test_") and file_name.endswith(".py")):
            continue
        with open(os.path.join(folder, file_name), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in tested:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    tested[node.func.attr].add(node.args[0].value)
    for kind, names in tested.items():
        missing = sorted(set(COMMANDS) - names)
        assert not missing, f"commands without a {kind} test: {missing}"


run(globals())
