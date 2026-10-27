from .. import limits
from ..errors import bad_args
from ..registry import command
from ..schema import boolean, integer, names, number
from ..texel import average_island_scale, pack, scale_to_density
from .uv import uv_mesh_object, uv_report


@command(
    "uv_pack",
    "Pack the UV islands of one or more meshes into the UV square, as one shared atlas or each on its own.",
    {
        "names": names("Mesh objects whose UVs to pack."),
        "margin": number("Space between islands, as a share of the UV square.", 0.0, 0.5, 0.01),
        "rotate": boolean("Allow rotating islands for a tighter fit.", True),
        "shared": boolean("Pack every object's islands together into one atlas; false packs each object on its own.", True),
        "uniform_density": boolean("In a shared atlas, give every island of every object the same texel density first.", True),
        "texel_density": number(
            "Scale the islands to this many pixels per metre and pack them without rescaling; they may spill out of the square.",
            maximum=limits.MAX_TEXEL_DENSITY,
            exclusive_minimum=0.0,
        ),
        "texture_size": integer("Texture size in pixels that texel densities refer to.", 1, limits.MAX_TEXTURE_SIZE, 1024),
    },
    ["names"],
)
def uv_pack(ctx, args):
    objects = [uv_mesh_object(name) for name in args["names"]]
    if len({obj.name for obj in objects}) != len(objects):
        raise bad_args("each object may be listed once")
    if len({obj.data.as_pointer() for obj in objects}) != len(objects):
        raise bad_args("two of the objects share one mesh")
    for obj in objects:
        if obj.data.uv_layers.active is None:
            raise bad_args(f"{obj.name} has no UV map; unwrap it first")
    size = args["texture_size"]
    for obj in objects:
        ctx.txn.touch_mesh(obj.data)
    fixed = "texel_density" in args
    if fixed:
        for obj in objects:
            scale_to_density(obj, obj.data.uv_layers.active, args["texel_density"], size)
    elif args["shared"] and args["uniform_density"]:
        average_island_scale(ctx.view_layer, objects)
    groups = [objects] if args["shared"] else [[obj] for obj in objects]
    for group in groups:
        pack(ctx.view_layer, group, args["margin"], args["rotate"], not fixed)
    return {
        "shared": args["shared"],
        "objects": [uv_report(obj, texture_size=size) for obj in objects],
    }
