"""The fluvial_terrain command: a range carved by rivers, as tiles."""

import numpy

from .. import fluvial_mesh, fluvial_presets, fluvial_run
from ..fluvial_model import WORLD_EDGES
from ..fluvial_fields import UPLIFT_SHAPES
from ..limits import FRACTION, MAX_MESH_VERTICES, MAX_SEED, TURN
from ..limits_fluvial import (LEAST_AREA_EXPONENT, LEAST_FLUVIAL_CELL, LEAST_FLUVIAL_SIDE, MAX_AREA_EXPONENT, MAX_CHANNEL_AREA,
                              MAX_DIFFUSIVITY, MAX_ERODIBILITY, MAX_FLUVIAL_CELL, MAX_FLUVIAL_LODS, MAX_FLUVIAL_SIDE, MAX_FLUVIAL_SIZE,
                              MAX_FLUVIAL_TILES, MAX_HILLSLOPE_GRADIENT, MAX_LITHOLOGY_BANDS, MAX_LITHOLOGY_FACTOR, MAX_UPLIFT_RATE)
from ..limits_land import LEAST_LAND_DISTANCE
from ..limits import MAX_LENGTH
from ..limits_parts import PATH_LENGTH
from ..errors import bad_args
from ..registry import COMMANDS, command
from ..schema import CREATES, array, boolean, integer, number, ref, string, validate
from .. import terrain_kernels

DEFAULT_SIZE_KM = 61.41
DEFAULT_CELL = 30.0
SETTING_FIELDS = ("uplift_rate", "uplift_shape", "crest", "behind", "along", "erodibility", "area_exponent", "diffusivity",
                  "critical_slope", "threshold_slope", "channel_area", "carve", "seed")


def grid_side(args):
    return int(round(args["size"] * 1000.0 / args["cell"])) + 1


def fluvial_rules(args):
    problems = []
    side = grid_side(args)
    tiles = args["tiles"]
    if not LEAST_FLUVIAL_SIDE.plain() <= side <= MAX_FLUVIAL_SIDE.plain():
        problems.append({"argument": "args.size", "value": args["size"],
                         "limit": {"name": MAX_FLUVIAL_SIDE.key, "value": MAX_FLUVIAL_SIDE.plain()},
                         "message": f"args.size {args['size']:g} km at args.cell {args['cell']:g} m makes {side} cells a side; the grid takes "
                                    f"{LEAST_FLUVIAL_SIDE.plain()} to {MAX_FLUVIAL_SIDE.plain()} ({MAX_FLUVIAL_SIDE.reason})",
                         "instead": "a larger cell for a larger domain, or a smaller one for a smaller domain"})
    per_tile = ((side - 1) // tiles + 2) ** 2
    if per_tile > MAX_MESH_VERTICES.plain():
        problems.append({"argument": "args.tiles", "value": tiles, "limit": {"name": MAX_MESH_VERTICES.key, "value": MAX_MESH_VERTICES.plain()},
                         "message": f"{tiles} tiles a side of a {side}-cell grid hold about {per_tile} vertices each, past the mesh vertex limit",
                         "instead": "more tiles"})
    return problems


@command(
    "fluvial_terrain",
    "Grow a mountain range tens of km across from tectonic uplift and river incision over millions of years, with its river network, lakes and drainage attributes.",
    {
        "name": ref(string("Base name of the tiles; they are named name_i_j and must be unused."), "object", CREATES),
        "preset": string("Starting parameters: young_alpine, mature_mountain or dissected_plateau; every other argument overrides one of them.",
                         list(fluvial_presets.PRESETS), "young_alpine"),
        "size": number("Side of the square domain in km.", None, MAX_FLUVIAL_SIZE, DEFAULT_SIZE_KM, exclusive_minimum=0.0),
        "cell": number("Cell size of the finest grid in metres.", LEAST_FLUVIAL_CELL, MAX_FLUVIAL_CELL, DEFAULT_CELL),
        "base_level": array(string("A side: north (+Y), south, east or west.", list(WORLD_EDGES)),
                            "Sides held at base level, where the rivers leave; the others are closed. Default: the preset's.", 1, len(WORLD_EDGES)),
        "uplift_rate": number("Largest rock uplift rate in m/yr.", None, MAX_UPLIFT_RATE, exclusive_minimum=0.0),
        "uplift_shape": string("block: everywhere; range: rising from the base level to a crest line; tilted; dome; array (uplift_file).", list(UPLIFT_SHAPES)),
        "crest": number("range: where the crest line lies, as a share of the farthest distance from the base level.", None, FRACTION, exclusive_minimum=0.0),
        "behind": number("range: uplift at the far side behind the crest, as a share of the crest's.", 0.0, FRACTION),
        "along": number("Variation of the uplift along the range, a share of it.", 0.0, FRACTION),
        "uplift_file": string("array: a .npy grid of uplift rates in m/yr in the workspace, resampled to the domain (row 0 at the south).", max_length=PATH_LENGTH),
        "erodibility": number("Stream-power erodibility K in m^(1-2m)/yr.", None, MAX_ERODIBILITY, exclusive_minimum=0.0),
        "area_exponent": number("Stream-power area exponent m; the slope exponent n is 1.", LEAST_AREA_EXPONENT, MAX_AREA_EXPONENT),
        "diffusivity": number("Hillslope diffusivity D in m^2/yr.", 0.0, MAX_DIFFUSIVITY),
        "critical_slope": number("Critical gradient of the non-linear hillslope diffusion (Roering et al. 1999).", None, MAX_HILLSLOPE_GRADIENT, exclusive_minimum=0.0),
        "threshold_slope": number("A fixed steepest hillslope gradient instead of the preset's critical angles drawn afresh every step.", None, MAX_HILLSLOPE_GRADIENT, exclusive_minimum=0.0),
        "channel_area": number("Drainage area of a channel head in m^2 at a gradient of 0.6; steeper ground starts channels at smaller areas (A S^2 constant).", 0.0, MAX_CHANNEL_AREA),
        "lithology": array(number("Erodibility factor of a band of rock.", None, MAX_LITHOLOGY_FACTOR, exclusive_minimum=0.0),
                           "Factors of repeating bands of rock that multiply the erodibility (below 1 harder).", 1, MAX_LITHOLOGY_BANDS),
        "band_width": number("Width of a lithology band in km.", None, MAX_FLUVIAL_SIZE, 5.0, exclusive_minimum=0.0),
        "band_angle": number("Direction the bands repeat along, degrees from +X.", 0.0, TURN, 0.0),
        "carve": boolean("Lake routing carves through the sills (true) or fills the lakes to their spill points (false).", True),
        "seed": integer("Seed of the starting relief and of the uplift's variation along the range.", 0, MAX_SEED, 0),
        "tiles": integer("Tiles a side.", 1, MAX_FLUVIAL_TILES, 4),
        "path": string("Optional .npz file in the workspace for every output grid.", max_length=PATH_LENGTH),
        "lods": integer("Levels of detail made for every tile by generate_lods.", 0, MAX_FLUVIAL_LODS, 0),
        "horizon": number("When given, distant_land continues the range this many metres past the domain.", LEAST_LAND_DISTANCE, MAX_LENGTH),
    },
    ["name"],
    rules=fluvial_rules,
    slow=True,
    writes_files=True,
    destructive=True,
    destructive_when="path names an existing file",
    family="shapes",
    intents=("mountain range tens of kilometres across shaped by rivers", "landscape evolution with tectonic uplift and river incision",
             "dendritic river network, lakes and Strahler orders over a range"),
    nearest=(("heightfield", "for noise terrain tiles"), ("erode", "to wear existing tiles with droplets and talus")),
)
def fluvial_terrain(ctx, args):
    settings = fluvial_presets.preset(args["preset"])
    for key in SETTING_FIELDS:
        if key in args:
            settings[key] = args[key]
    if "threshold_slope" in args:
        settings["threshold_angles"] = None
    if "base_level" in args:
        settings["base_level"] = list(dict.fromkeys(args["base_level"]))
    if "lithology" in args:
        settings["lithology"] = {"factors": args["lithology"], "band_share": args["band_width"] / args["size"], "angle": args["band_angle"]}
    if settings.get("uplift_shape") == "array":
        if "uplift_file" not in args:
            raise bad_args("args.uplift_shape 'array' needs args.uplift_file, a .npy grid of uplift rates")
        settings["uplift_values"] = numpy.load(ctx.workspace.existing(args["uplift_file"], (".npy",)))
    side = grid_side(args)
    cell = args["size"] * 1000.0 / (side - 1)
    settings["threads"] = terrain_kernels.default_threads()
    output = ctx.workspace.output(args["path"], (".npz",)) if "path" in args else None
    run = fluvial_run.run(settings, side, cell)
    tiles = fluvial_mesh.build_tiles(ctx, args["name"], run["grids"], cell, args["tiles"])
    result = {"tiles": tiles, "side": side, "cell": round(cell, 6), "extent_km": round((side - 1) * cell / 1000.0, 6),
              "attributes": dict(fluvial_mesh.ATTRIBUTES), "measures": run["summary"], "rivers": run["rivers"], "lakes": run["lakes"],
              "settings": {key: value for key, value in run["settings"].items() if key not in ("uplift_values", "threads")}}
    if output is not None:
        fluvial_mesh.save_grids(output, run["grids"], cell)
        result["path"] = ctx.workspace.relative(output)
    if "horizon" in args:
        land = validate(COMMANDS["distant_land"].schema, {"name": f"{args['name']}_horizon", "terrain": tiles, "distance": args["horizon"], "style": "ranges"})
        result["horizon"] = COMMANDS["distant_land"].run(ctx, land)
    if args["lods"]:
        lods = validate(COMMANDS["generate_lods"].schema, {"names": tiles, "count": args["lods"], "ratios": [0.5 ** (level + 1) for level in range(args["lods"])]})
        result["lods"] = COMMANDS["generate_lods"].run(ctx, lods)
        result["tiles"] = [f"{tile}_LOD0" for tile in tiles]
    return result
