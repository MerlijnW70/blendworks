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
    "add_material", "assign_material", "vertex_colors",
    "uv_smart_project", "uv_unwrap", "uv_info",
    "add_light", "add_camera", "look_at", "set_world",
    "render_preview", "export", "save_blend", "import",
}
ASSET_LIBRARY_COMMANDS = {"set_world_hdri"}
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
    python = Bridge(bridge.workspace, allow_python=True)
    assert sorted(entry["name"] for entry in python.ok("describe")["commands"]) == sorted(COMMANDS)


def test_every_design_command_exists(bridge):
    names = set(bridge.handler.registry.names())
    assert DESIGN_COMMANDS <= names, sorted(DESIGN_COMMANDS - names)
    assert ASSET_LIBRARY_COMMANDS <= names, sorted(ASSET_LIBRARY_COMMANDS - names)
    assert set(COMMANDS) - DESIGN_COMMANDS - ASSET_LIBRARY_COMMANDS == {"run_python"}


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
