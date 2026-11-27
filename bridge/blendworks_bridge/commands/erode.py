import time

import numpy

from ..erosion_droplets import hydraulic_erode
from ..erosion_thermal import max_slope_degrees, thermal_erode
from ..errors import bad_args
from ..heightgrid import TileSet
from ..mesh_attributes import ATTRIBUTES, write_attributes
from ..limits import (FRACTION, LEAST_TALUS_ANGLE, MAX_DROPLET_GRAVITY, MAX_DROPLET_INERTIA, MAX_DROPLET_LIFETIME,
                      MAX_DROPLETS as DROPLET_LIMIT, MAX_EROSION_BRUSH, MAX_EROSION_TILES, MAX_LENGTH, MAX_RELIEF, MAX_SEDIMENT_CAPACITY,
                      MAX_SEED, MAX_TALUS_ANGLE, MAX_THERMAL_SWEEPS, SHORTEST_DROPLET_STEP, SMALLEST_EROSION_BRUSH)
from ..registry import command
from ..schema import EXISTS, integer, names, number, ref, string
from ..util import get_mesh_object, rounded

MAX_DROPLETS = DROPLET_LIMIT
MAX_SWEEPS = MAX_THERMAL_SWEEPS
ROUNDS = 20
HYDRAULIC_KEYS = ("inertia", "capacity", "min_capacity", "erode_rate", "deposit_rate", "evaporation", "gravity", "radius", "max_lifetime", "step")


def tile_objects(args):
    wanted = [args["name"]] + [name for name in args.get("names", []) if name != args["name"]]
    objects = []
    for name in wanted:
        if name in [obj.name for obj in objects]:
            raise bad_args(f"{name} is listed twice")
        objects.append(get_mesh_object(name))
    return objects


def hydraulic_settings(args):
    return {key: args[key] for key in HYDRAULIC_KEYS}


def interleaved(heights, free, spacing, args):
    rounds = min(ROUNDS, args["droplets"])
    sweeps_each = max(1, args["iterations"] // rounds)
    carried = 0.0
    sweeps = 0
    settled = False
    for index in range(rounds):
        share = args["droplets"] // rounds + (args["droplets"] % rounds if index == rounds - 1 else 0)
        carried += hydraulic_erode(heights, free, spacing, hydraulic_settings(args), share, [args["seed"], index])
        done, settled = thermal_erode(heights, free, spacing, args["talus_angle"], args["rate"], sweeps_each)
        sweeps += done
    return carried, {"sweeps": sweeps, "settled": settled, "rounds": rounds}


def refresh_attributes(tile):
    present = [name for name in ATTRIBUTES if name in tile.obj.data.attributes]
    if not present:
        return {}
    faces = (tile.resolution - 1) ** 2
    return write_attributes(tile.obj, present, faces, tile.resolution**2)


@command(
    "erode",
    "Erode heightfield terrain in metres: thermal talus slides, hydraulic droplets or both; tile edges stay fixed; writes erosion and deposition attributes and reports the volumes.",
    {
        "name": ref(string("Heightfield tile to erode (a mesh built by heightfield, with or without skirt, moved or scaled but not rotated)."), "object", EXISTS),
        "names": ref(names("Neighbouring tiles to erode together with name as one grid, written back with shared edges equal; they must form a complete rectangle of equal tiles. Without them the edge heights of name stay unchanged.", 1, MAX_EROSION_TILES), "object", EXISTS),
        "mode": string("thermal slides material down slopes past the talus angle; hydraulic runs droplets; both runs the droplets in 20 rounds, each followed by thermal sweeps, so gully walls settle at the talus angle as they form.", ["thermal", "hydraulic", "both"], "both"),
        "iterations": integer("Thermal sweeps (they stop early once no slope exceeds talus_angle by more than 0.05 degrees); in both mode the total, split over the 20 rounds.", 1, MAX_SWEEPS, 100),
        "seed": integer("Seed of the droplet start points: the same seed gives the same heights.", 0, MAX_SEED, 0),
        "talus_angle": number("Thermal: steepest stable slope in degrees from horizontal.", LEAST_TALUS_ANGLE, MAX_TALUS_ANGLE, 35.0),
        "rate": number("Thermal: fraction of the excess moved per sweep.", 0.0, FRACTION, 0.5, exclusive_minimum=0.0),
        "droplets": integer("Hydraulic: number of droplets, started at random points of the grid.", 1, MAX_DROPLETS, 20_000),
        "inertia": number("Hydraulic: how much a droplet keeps its direction, 0 follows the slope exactly.", 0.0, MAX_DROPLET_INERTIA, 0.05),
        "capacity": number("Hydraulic: Kc in C = Kc * sin(slope) * speed * water.", 0.0, MAX_SEDIMENT_CAPACITY, 4.0),
        "min_capacity": number("Hydraulic: lowest capacity in metres, so droplets on flat ground still carry a little.", 0.0, MAX_RELIEF, 0.01),
        "erode_rate": number("Hydraulic: fraction of the missing capacity picked up per step.", 0.0, FRACTION, 0.3),
        "deposit_rate": number("Hydraulic: fraction of the excess sediment dropped per step.", 0.0, FRACTION, 0.3),
        "evaporation": number("Hydraulic: fraction of the water lost per step.", 0.0, FRACTION, 0.01),
        "gravity": number("Hydraulic: how fast a droplet speeds up per metre it descends.", 0.0, MAX_DROPLET_GRAVITY, 4.0),
        "radius": number("Hydraulic: erosion brush radius in metres, at least 1.5 grid spacings.", SMALLEST_EROSION_BRUSH, MAX_EROSION_BRUSH, 3.0),
        "max_lifetime": integer("Hydraulic: steps a droplet lives.", 1, MAX_DROPLET_LIFETIME, 30),
        "step": number("Hydraulic: metres a droplet moves per step, so the result does not depend on the grid spacing.", SHORTEST_DROPLET_STEP, MAX_LENGTH, 1.0),
        "mask": string("Vertex group or float point attribute (0 to 1) scaling how much each vertex may change; 0 protects it."),
    },
    ["name"],
    slow=True,
    family="shapes",
    intents=("erode terrain with thermal talus slopes and hydraulic droplets", "carve drainage channels and deposits into a heightfield", "weather a landscape so it stops looking like raw noise"),
    nearest=(("heightfield", "to build the terrain tiles first"), ("noise_displace", "for plain noise roughness with no erosion")),
)
def erode(ctx, args):
    started = time.perf_counter()
    tiles = TileSet(tile_objects(args))
    mode = args["mode"]
    before = tiles.heights()
    heights = before.copy()
    free = tiles.free_weights(args.get("mask"))
    spacing = tiles.spacing
    carried = 0.0
    result = {"name": args["name"], "tiles": [tile.obj.name for tile in tiles.tiles], "mode": mode, "grid": [tiles.shape[1], tiles.shape[0]], "spacing": [rounded(spacing[0], 9), rounded(spacing[1], 9)]}
    thermal = (heights, free, spacing, args["talus_angle"], args["rate"])
    if mode == "hydraulic":
        carried = hydraulic_erode(heights, free, spacing, hydraulic_settings(args), args["droplets"], args["seed"])
        result["droplets"] = args["droplets"]
    elif mode == "thermal":
        sweeps, settled = thermal_erode(*thermal, args["iterations"])
        result["thermal"] = {"sweeps": sweeps, "settled": settled}
    else:
        carried, result["thermal"] = interleaved(heights, free, spacing, args)
        result["droplets"] = args["droplets"]
    tiles.write(before, heights)
    area = spacing[0] * spacing[1]
    change = heights - before
    result["eroded_volume"] = rounded(float(numpy.maximum(-change, 0.0).sum() * area), 9)
    result["deposited_volume"] = rounded(float(numpy.maximum(change, 0.0).sum() * area), 9)
    result["carried_off_volume"] = rounded(carried, 9)
    result["max_slope"] = rounded(max_slope_degrees(heights, free, spacing), 6)
    result["edge_change"] = rounded(float(max(numpy.abs(change[0]).max(), numpy.abs(change[-1]).max(), numpy.abs(change[:, 0]).max(), numpy.abs(change[:, -1]).max())), 12)
    result["height_range"] = [rounded(float(heights.min()), 9), rounded(float(heights.max()), 9)]
    ctx.view_layer.update()
    result["attributes"] = {tile.obj.name: refresh_attributes(tile) for tile in tiles.tiles if any(name in tile.obj.data.attributes for name in ATTRIBUTES)}
    result["seconds"] = rounded(time.perf_counter() - started, 3)
    return result
