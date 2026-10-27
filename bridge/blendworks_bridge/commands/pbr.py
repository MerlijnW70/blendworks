import bpy

from ..errors import bad_args
from ..images import IMAGE_EXTENSIONS, NOT_IMAGES, flipped_green, get_image, load_image, loaded_from
from ..pbr import DEFAULT_OPTIONS, MAP_KEYS, ORM_ORDERS, assign_colorspaces, build_pbr, check_uv_map, warnings_for
from ..registry import command
from ..schema import array, number, string

MAP_LABELS = {
    "base_color": "base colour (sRGB)",
    "metallic": "metallic (non-colour, red channel)",
    "roughness": "roughness (non-colour, red channel)",
    "orm": "combined occlusion-roughness-metallic (non-colour, channel order from orm_order)",
    "normal": "tangent-space normal map (non-colour)",
    "height": "height map applied as a bump (non-colour, red channel)",
    "emission": "emission colour (sRGB)",
    "alpha": "opacity (non-colour, red channel; the base colour image's alpha when it is the same image)",
    "ao": "ambient occlusion, exported as the glTF occlusion texture (non-colour, red channel)",
}


def map_properties():
    properties = {}
    for key in MAP_KEYS:
        properties[key] = string(f"Name of a loaded image for the {MAP_LABELS[key]}.")
        properties[f"{key}_path"] = string(f"Workspace path of an image file for the {MAP_LABELS[key]}.", max_length=1024)
    return properties


PROPERTIES = dict(
    {"name": string("Material name; created, or rebuilt when it exists.")},
    **map_properties(),
    orm_order=string("Channel order of the orm map, red first: o occlusion, r roughness, m metallic.", list(ORM_ORDERS), "orm"),
    normal_convention=string("opengl (+Y, Blender and glTF) or directx (-Y, flipped on load).", ["opengl", "directx"], "opengl"),
    normal_strength=number("Normal map strength.", 0.0, 10.0, 1.0),
    height_strength=number("Bump strength of the height map.", 0.0, 10.0, 1.0),
    height_distance=number("Height in metres of the full 0 to 1 height range.", 0.0, 10.0, 0.01),
    emission_strength=number("Emission strength.", 0.0, 1000.0, 1.0),
    uv_map=string("UV map to sample. Default: the mesh's active render UV map."),
    scale=array({"type": "number", "minimum": 0.001, "maximum": 1000.0}, "Texture repeats along U and V.", 2, 2, [1.0, 1.0]),
    offset=array({"type": "number", "minimum": -1000.0, "maximum": 1000.0}, "Texture offset along U and V.", 2, 2, [0.0, 0.0]),
    rotation=number("Texture rotation in degrees.", -360.0, 360.0, 0.0),
)


@command(
    "material_pbr",
    "Build a Principled BSDF material from PBR image maps with the right colour spaces, ready for glTF export.",
    PROPERTIES,
    ["name"],
    family="materials",
    intents=("PBR material from my image maps", "albedo, normal, roughness and ORM textures from files"),
    nearest=(("library_apply", "for Poly Haven textures"),),
)
def material_pbr(ctx, args):
    maps = collect_maps(ctx, args)
    if "orm" in maps and ("metallic" in maps or "roughness" in maps):
        raise bad_args("give orm or metallic and roughness, not both")
    material = bpy.data.materials.get(args["name"])
    if "uv_map" in args and material is not None:
        check_uv_map(material, args["uv_map"])
    if args["normal_convention"] == "directx" and "normal" in maps:
        maps["normal"] = flipped_green(maps["normal"], f"{maps['normal'].name}_opengl")
    created = material is None
    if created:
        material = bpy.data.materials.new(args["name"])
        material.use_fake_user = True
    ctx.txn.guard_image_pixels()
    colorspaces = assign_colorspaces(ctx.txn, maps)
    options = {key: args.get(key, default) for key, default in DEFAULT_OPTIONS.items()}
    options["uv_map"] = args.get("uv_map")
    build_pbr(material, maps, options)
    return {
        "name": material.name,
        "created": created,
        "maps": {key: image.name for key, image in maps.items()},
        "colorspaces": colorspaces,
        "uv_map": options["uv_map"],
        "warnings": warnings_for(maps),
    }


def collect_maps(ctx, args):
    maps = {}
    for key in MAP_KEYS:
        path_key = f"{key}_path"
        if key in args and path_key in args:
            raise bad_args(f"give {key} or {path_key}, not both")
        if key in args:
            maps[key] = get_image(args[key])
        elif path_key in args:
            resolved = ctx.workspace.existing(args[path_key], IMAGE_EXTENSIONS)
            maps[key] = loaded_from(resolved) or load_image(ctx.workspace, args[path_key])
    if not maps:
        raise bad_args(f"give at least one map: {', '.join(MAP_KEYS)}")
    for key, image in maps.items():
        if image.type in NOT_IMAGES or tuple(image.size) == (0, 0):
            raise bad_args(f"image {image.name} for {key} has no pixels")
    return maps
