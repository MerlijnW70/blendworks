from .. import limits
from ..errors import bad_args
from ..registry import command
from ..schema import boolean, integer, names, number, string
from ..texel import average_island_scale, margin_memory, pack, scale_to_density
from ..uv_coverage import pack_for_coverage
from .uv import uv_mesh_object, uv_report

TARGETS = ("fit", "coverage")
COVERAGE_ONLY = ("min_island_area", "time_limit")


def object_group(args):
    objects = [uv_mesh_object(name) for name in args["names"]]
    if len({obj.name for obj in objects}) != len(objects):
        raise bad_args("each object may be listed once")
    if len({obj.data.as_pointer() for obj in objects}) != len(objects):
        raise bad_args("two of the objects share one mesh")
    for obj in objects:
        if obj.data.uv_layers.active is None:
            raise bad_args(f"{obj.name} has no UV map; unwrap it first")
    return objects


def summary(reports):
    densities = [report["texel_density"] for report in reports]
    uv_area = sum(report["uv_area"] for report in reports)
    return {
        "texture_size": densities[0]["texture_size"],
        "mean": round(sum(item["mean"] for item in densities) / len(densities), 3),
        "min": min(item["min"] for item in densities),
        "max": max(item["max"] for item in densities),
        "uv_area": round(uv_area, 4),
    }


@command(
    "uv_pack",
    "Pack the UV islands of one or more meshes into the UV square as one shared atlas or each on its own; target coverage merges slivers, evens the texel density and searches the packing.",
    {
        "names": names("Mesh objects whose UVs to pack."),
        "target": string("fit: one packing pass. coverage: merge tiny islands, even out the texel density, then search margin, rotation and shape for the best coverage.", TARGETS, "fit"),
        "margin": number("Space between islands, as a share of the UV square; with target coverage the largest margin the search tries.", 0.0, 0.5, 0.01),
        "rotate": boolean("Allow rotating islands for a tighter fit.", True),
        "shared": boolean("Pack every object's islands together into one atlas; false packs each object on its own.", True),
        "uniform_density": boolean("In a shared atlas, give every island of every object the same texel density first; target coverage always does.", True),
        "min_island_area": number("target coverage: merge islands under this share of the surface area into a neighbour where the seams allow. Default 0.002.", 0.0, 1.0),
        "time_limit": number("target coverage: seconds the packing search may run; it stops after the trial that passes it. Default 30.", 1.0, 300.0),
        "texel_density": number(
            "Scale the islands to this many pixels per metre and pack them without rescaling; they may spill out of the square.",
            maximum=limits.MAX_TEXEL_DENSITY,
            exclusive_minimum=0.0,
        ),
        "texture_size": integer("Texture size in pixels that texel densities refer to; the coverage search keeps at least 2 texels between islands.", 1, limits.MAX_TEXTURE_SIZE, 1024),
    },
    ["names"],
    slow=True,
    family="uv",
    intents=("pack UV islands into one atlas", "repack islands with a margin"),
    nearest=(("uv_info", "to measure UVs"),),
)
def uv_pack(ctx, args):
    objects = object_group(args)
    size = args["texture_size"]
    groups = [objects] if args["shared"] else [[obj] for obj in objects]
    if args["target"] == "coverage":
        if "texel_density" in args:
            raise bad_args("target coverage evens the density itself; texel_density belongs to target fit")
        with margin_memory():
            search = pack_for_coverage(ctx, groups, args, size)
    else:
        for name in COVERAGE_ONLY:
            if name in args:
                raise bad_args(f"{name} belongs to target coverage")
        search = None
        fixed = "texel_density" in args
        if fixed:
            for obj in objects:
                scale_to_density(obj, obj.data.uv_layers.active, args["texel_density"], size)
        elif args["shared"] and args["uniform_density"]:
            average_island_scale(ctx.view_layer, objects)
        for group in groups:
            pack(ctx.view_layer, group, args["margin"], args["rotate"], not fixed)
    reports = [uv_report(obj, texture_size=size) for obj in objects]
    result = {"shared": args["shared"], "target": args["target"], "objects": reports, "coverage": coverage_of(reports), "texel_density": summary(reports)}
    if search is not None:
        result["search"] = search
    return result


def coverage_of(reports):
    return round(sum(report["coverage"] for report in reports) / len(reports), 4) if reports else 0.0
