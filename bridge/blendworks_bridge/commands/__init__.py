import importlib

MODULES = (
    "scene",
    "objects",
    "transforms",
    "mesh_edit",
    "modifiers",
    "geometry",
    "shapes",
    "solids",
    "placement",
    "roller_chain",
    "mesh_query",
    "wear",
    "materials",
    "images",
    "pbr",
    "procedural",
    "bake",
    "uv",
    "uv_pack",
    "lights",
    "render",
    "files",
    "run_python",
)


def load():
    for name in MODULES:
        importlib.import_module(f"{__name__}.{name}")
