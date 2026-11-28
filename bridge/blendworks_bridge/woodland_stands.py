"""Stand schema and footprints.

The stands of a woodland call: their schema and their footprints. Copses and groves are discs, hedgerows bands along
lines or closed field edges, forests polygons or the patches of a distant forest's field, and copses scatters copses
over an area by a hard-core process on dry, gentle ground."""
import json
import math

import numpy

from .commands.distant_forest import FIELD_PROPERTY
from .errors import bad_args
from .land_field import smoothstep
from .limits import FEWEST_SIDES, MAX_COORDINATE, MAX_COPSES, MAX_CURVE_POINTS, MAX_SEED, PAIR
from .schema import EXISTS, array, boolean, integer, length, obj, ref, string
from .tree_species import SHRUB_NAMES, TREE_NAMES
from .util import get_object
from .woodland_pattern import matern_centres, poisson_rectangle
from .woodland_shapes import Band, Disc, Polygon, Raster, forest_field

STAND_KINDS = ("copse", "grove", "hedgerow", "forest", "copses")
POINT = {"type": "array", "items": {"type": "number", "minimum": -MAX_COORDINATE, "maximum": MAX_COORDINATE}, "minItems": 2, "maxItems": 3}
COPSE_GAP = 2.5
COPSE_SPREAD = 0.3
COPSE_CANDIDATES = 4.0

STAND = obj(
    {
        "kind": string("copse: a small dense wood with a full edge; grove: trees with little undergrowth; hedgerow: a band of shrubs with standard trees along line; forest: a wood within outline or the patches of field; copses: count copses scattered over the area of centre and radius or outline.", STAND_KINDS),
        "centre": array({"type": "number", "minimum": -MAX_COORDINATE, "maximum": MAX_COORDINATE}, "copse, grove, copses: centre [x, y] in metres.", 2, 2),
        "radius": length("copse, grove, copses: radius in metres."),
        "line": array(POINT, "hedgerow: the line [x, y] points it follows, such as a field edge.", PAIR, MAX_CURVE_POINTS),
        "closed": boolean("hedgerow: join the last point to the first, round a field.", False),
        "width": length("hedgerow: width of the band in metres.", 4.0),
        "outline": array(POINT, "forest or copses: the area's corners [x, y] in metres.", FEWEST_SIDES, MAX_CURVE_POINTS),
        "field": ref(string("forest: a distant_forest group; the stand takes its patches inside the ground, so it runs on into the far forest."), "object", EXISTS),
        "water_margin": length("forest with field: metres of open shore kept between water and the stand.", 15.0),
        "count": integer("copses: how many copses.", 1, MAX_COPSES),
        "copse_radius": length("copses: mean copse radius in metres; each copse varies by about a third.", 15.0),
        "species": array({"type": "string", "enum": list(TREE_NAMES)}, "Tree species of this stand. Default the call's species, or the field forest's.", 1, len(TREE_NAMES)),
        "shrubs": array({"type": "string", "enum": list(SHRUB_NAMES)}, "Shrub species of this stand. Default the call's shrubs.", 1, len(SHRUB_NAMES)),
        "seed": integer("Seed of this stand's rim and copses; default its index.", 0, MAX_SEED),
    },
    ["kind"],
)


def need(stand, index, keys):
    missing = [key for key in keys if key not in stand]
    if missing:
        raise bad_args(f"stands[{index}] ({stand['kind']}) needs {', '.join(missing)}")


def area_footprint(stand, index, seed, args):
    if "outline" in stand:
        return Polygon("forest", stand["outline"], seed, 0.0, args["rim_wavelength"])
    need(stand, index, ("centre", "radius"))
    return Disc("forest", stand["centre"], stand["radius"], seed, 0.0, args["rim_wavelength"])


def scattered_copses(stand, index, seed, args, site):
    need(stand, index, ("count",))
    area = area_footprint(stand, index, seed, args)
    rng = numpy.random.default_rng([seed, 7])
    low, high = area.bounds(0.0)
    radius = stand["copse_radius"]
    candidates = poisson_rectangle(rng, low, high, COPSE_CANDIDATES / (math.pi * radius * radius))
    candidates = candidates[area.signed(candidates) >= 0.0]
    weights = site(candidates)["ok"].astype(numpy.float64) if len(candidates) else numpy.zeros(0)
    centres = matern_centres(rng, candidates[weights > 0.0], weights[weights > 0.0], stand["count"], COPSE_GAP * radius)
    radii = radius * numpy.exp(rng.normal(0.0, COPSE_SPREAD, len(centres)))
    return [Disc("copse", centre, size, seed * 101 + number, args["rim_wander"], args["rim_wavelength"]) for number, (centre, size) in enumerate(zip(centres.tolist(), radii.tolist()))]


def field_footprint(stand, index, seed, args, site):
    group = get_object(stand["field"])
    record = group.get(FIELD_PROPERTY)
    if not isinstance(record, str):
        raise bad_args(f"stands[{index}].field: {group.name} is not a distant_forest group")
    settings = json.loads(record)
    share = forest_field(settings)
    margin = stand["water_margin"]

    def share_of(xy):
        values = share(xy)
        dry = numpy.ones(len(xy))
        heights, _ = site.surface(xy)
        on = ~numpy.isnan(heights)
        if site.water.empty or not on.any():
            return values * on
        depth = numpy.full(len(xy), -margin)
        depth[on] = site.water.signed_depth(numpy.column_stack([xy[on], heights[on]]), margin)
        dry = smoothstep(0.0, margin, -depth)
        return values * dry * on

    raster = Raster("forest", site.low, site.high, share_of, seed, args["rim_wander"], args["rim_wavelength"])
    return raster, [name for name in settings.get("species", []) if name in TREE_NAMES], settings


def footprints_of(args, site):
    """(footprint, tree species, shrub species, report) for every stand, copses expanded into their copses."""
    found = []
    for index, stand in enumerate(args["stands"]):
        kind = stand["kind"]
        seed = stand.get("seed", args["seed"] * 131 + index)
        species = stand.get("species", args["species"])
        shrubs = stand.get("shrubs", args["shrubs"])
        if kind in ("copse", "grove"):
            need(stand, index, ("centre", "radius"))
            found.append((Disc(kind, stand["centre"], stand["radius"], seed, args["rim_wander"], args["rim_wavelength"]), species, shrubs, {"from": index}))
        elif kind == "hedgerow":
            need(stand, index, ("line",))
            found.append((Band(kind, stand["line"], stand["width"], stand["closed"], seed, args["rim_wander"], args["rim_wavelength"]), species, shrubs, {"from": index}))
        elif kind == "forest" and "field" in stand:
            raster, field_species, settings = field_footprint(stand, index, seed, args, site)
            chosen = stand.get("species", field_species or args["species"])
            found.append((raster, chosen, shrubs, {"from": index, "field": stand["field"], "field_share": round(raster.inside_share, 4), "patch_size": settings["patch_size"]}))
        elif kind == "forest":
            need(stand, index, ("outline",))
            found.append((Polygon(kind, stand["outline"], seed, args["rim_wander"], args["rim_wavelength"]), species, shrubs, {"from": index}))
        else:
            copses = scattered_copses(stand, index, seed, args, site)
            found.extend((copse, species, shrubs, {"from": index}) for copse in copses)
    if not found:
        raise bad_args("the stands found no ground to grow on")
    return found
