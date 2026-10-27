import importlib

MODULES = (
    "scene",
    "objects",
    "hierarchy",
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
    "noise_displace",
    "heightfield",
    "clean",
    "engrave",
    "scales",
    "materials",
    "images",
    "pbr",
    "procedural",
    "material_nodes",
    "bake",
    "uv",
    "uv_pack",
    "lods",
    "lights",
    "render",
    "files",
    "run_python",
    "checkpoints",
)


def load():
    for name in MODULES:
        importlib.import_module(f"{__name__}.{name}")
