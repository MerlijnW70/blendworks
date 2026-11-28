"""The generate_lods command: LOD copies of a mesh by decimation that keeps UVs and borders."""

import os
import sys

from ..errors import bad_args
from ..limits import MAX_LOD_LEVELS, MAX_LOD_RATIO
from ..registry import command
from ..schema import EXISTS, array, boolean, integer, names, number, ref
from ..util import GEOMETRY_TYPES, get_mesh_object

PACKAGE_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "package")
MAX_LEVELS = MAX_LOD_LEVELS


def core():
    if PACKAGE_FOLDER not in sys.path:
        sys.path.insert(0, PACKAGE_FOLDER)
    import package_levels

    return package_levels


def rounded_level(level):
    entry = {
        "level": level["level"],
        "names": level["names"],
        "triangles": level["triangles"],
        "ratio": round(level["ratio"], 4),
    }
    if level["level"] == 0:
        return entry
    error = level["error"]
    entry.update(
        {
            "target_ratio": level["targetRatio"],
            "distance": round(level["distance"], 4),
            "screen_error_pixels": round(level["screenErrorPixels"], 4),
            "hausdorff": round(error["hausdorff"], 6),
            "hausdorff_fraction": round(error["hausdorffFraction"], 6),
            "mean_error": round(error["mean"], 6),
            "decimation": level["modes"],
        }
    )
    return entry


def plan_generate_lods(args, state):
    """Plan hook: <name>_LOD1..<name>_LOD<count> for every source, and the source renamed to <name>_LOD0."""
    if "names" not in args:
        state.unknown(("object",))
        return
    for name in args["names"]:
        for level in range(1, args["count"] + 1):
            state.add("object", f"{name}_LOD{level}")
        if args["rename_source"]:
            state.rename("object", name, f"{name}_LOD0")


@command(
    "generate_lods",
    "Make LOD1..LODn copies named <name>_LOD<n> by decimation that keeps borders, materials and UV seams, and report each one's error.",
    {
        "names": ref(names("Mesh objects to make levels for. Default: every visible mesh."), "object", EXISTS),
        "count": integer("Number of levels besides LOD0.", 1, MAX_LEVELS),
        "ratios": array({"type": "number", "exclusiveMinimum": 0, "maximum": MAX_LOD_RATIO}, "Triangle share of each level against LOD0, falling.", 1, MAX_LEVELS),
        "max_screen_error": number("Instead of ratios: the largest error in pixels on a 1080-pixel display with a 60 degree field of view.", None, None, None, 0.0),
        "distances": array({"type": "number", "exclusiveMinimum": 0}, "With max_screen_error: the distance in metres where each level is used, rising.", 1, MAX_LEVELS),
        "rename_source": boolean("Rename each source object to <name>_LOD0.", True),
    },
    ["count"],
    slow=True,
    plan=plan_generate_lods,
    family="lods",
    intents=("levels of detail for a game engine", "LOD copies with screen error"),
    nearest=(("decimate", "for one reduction in place"),),
)
def generate_lods(ctx, args):
    if "names" in args:
        sources = [get_mesh_object(name) for name in args["names"]]
    else:
        sources = [obj for obj in ctx.scene.objects if obj.type == "MESH" and obj.visible_get(view_layer=ctx.view_layer)]
    others = sorted({obj.type for obj in ctx.scene.objects if obj.type in GEOMETRY_TYPES and obj.type != "MESH" and "names" not in args})
    if others:
        raise bad_args(f"the scene has {', '.join(others).lower()} objects; convert them to meshes or name the mesh objects to use")
    levels = core()
    config = {"count": args["count"]}
    for field, key in (("ratios", "ratios"), ("max_screen_error", "maxScreenError"), ("distances", "distances")):
        if field in args:
            config[key] = args[field]
    try:
        built = levels.build_lods(sources, config, rename_source=args["rename_source"])
    except levels.LodError as error:
        raise bad_args(error.message) from None
    except ValueError as error:
        raise bad_args(str(error)) from None
    return {"levels": [rounded_level(level) for level in built["levels"]], "bounds_diagonal": round(built["diagonal"], 6)}
