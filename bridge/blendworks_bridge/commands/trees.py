import numpy

from ..kit_limits import DEFAULT_QUERY_PAGE, MAX_QUERY_PAGE, MAX_TREE_NODES, MAX_TREE_POINTS
from ..registry import command
from ..schema import array, described, integer, length, number, obj, string, vector3
from ..tree_plan import COLONIZATION_DEFAULTS, LEVELS_DEFAULTS, grow
from ..tree_shapes import SHAPES
from ..tree_skeleton import FORMAT, PROPERTY, VERSION, from_property, preview_curve
from ..util import get_object, link_object, require_free_name

METHODS = ("colonization", "levels")
MAX_LEVELS = 4


def per_level(item, description, default_note):
    return array(item, f"{description} One entry per level from the first branches outward; the last entry repeats for deeper levels. Default {default_note}.", 1, MAX_LEVELS)


def tropism(description):
    return array({"type": "number", "minimum": -4.0, "maximum": 4.0}, description, 3, 3)


ROOTS = described(
    obj(
        {
            "points": integer("Attraction points in the soil envelope.", 1, MAX_TREE_POINTS, 1500),
            "depth": length("Depth of the soil envelope below the trunk base, in metres.", 1.2),
            "radius": length("Largest radius of the soil envelope, in metres.", 2.5),
            "shape": string("Weber-Penn shape of the soil envelope, read downwards from the surface, so hemispherical is widest at the top.", SHAPES, "hemispherical"),
            "influence": length("Radius of influence di of a soil point, in metres.", 0.8),
            "kill": length("Kill distance dk in the soil, in metres.", 0.25),
            "step": length("Growth step D of a root, in metres.", 0.12),
            "tropism": tropism("Tropism vector g of the roots, added to each unit growth direction; downward by default.") | {"default": [0.0, 0.0, -0.4]},
            "tip_radius": length("Radius at every root tip, in metres. Default: tip_radius.", maximum=1.0),
        }
    ),
    "Grow roots by space colonisation in a soil envelope below the trunk base, joined to the tree at its base node.",
)

FIELDS = {
    "name": string("Name of the preview curve object that carries the skeleton.", default="Tree"),
    "method": string("colonization grows towards attraction points in a crown envelope (Runions et al. 2007); levels builds recursive stems (Weber and Penn 1995).", METHODS, "colonization"),
    "location": vector3("Where the trunk base stands, in world metres.", [0.0, 0.0, 0.0]),
    "seed": integer("Seed of the attraction points; the same seed and settings give the same skeleton whatever the face or point order.", 0, 2**31 - 1, 0),
    "height": length("colonization: top of the crown above the base; levels: trunk length; metres.", 8.0, maximum=1000.0),
    "trunk_height": number("colonization: trunk grown straight up before colonisation and bottom of a built-in crown; levels: bare trunk below the first branch; metres.", 0.0, 1000.0, 2.0),
    "envelope": string(f"Crown: a Weber-Penn shape ({', '.join(SHAPES)}) or, for colonization, the name of a closed mesh object.", default="spherical"),
    "crown_radius": length(f"colonization: largest radius of a built-in crown, in metres. Default {COLONIZATION_DEFAULTS['crown_radius']}.", maximum=1000.0),
    "points": integer(f"colonization: attraction points N in the crown. Default {COLONIZATION_DEFAULTS['points']}.", 1, MAX_TREE_POINTS),
    "influence": length(f"colonization: radius of influence di, in metres; a point attracts only its nearest node within it. Default {COLONIZATION_DEFAULTS['influence']}."),
    "kill": length(f"colonization: kill distance dk, in metres; a point closer to a node is removed. Default {COLONIZATION_DEFAULTS['kill']}."),
    "step": length(f"colonization: growth step D, in metres. Default {COLONIZATION_DEFAULTS['step']}."),
    "tropism": tropism("colonization: tropism vector g added to each normalised growth direction; it also leans the trunk. Default [0, 0, 0]."),
    "levels": integer(f"levels: stem levels including the trunk. Default {LEVELS_DEFAULTS['levels']}.", 1, MAX_LEVELS),
    "branches": per_level({"type": "integer", "minimum": 0, "maximum": 200}, "levels: children per stem; deeper stems get fewer when they are shorter.", LEVELS_DEFAULTS["branches"]),
    "down_angle": per_level({"type": "number", "minimum": 0.0, "maximum": 180.0}, "levels: angle between a child and its parent, in degrees.", LEVELS_DEFAULTS["down_angle"]),
    "rotate": per_level({"type": "number", "minimum": -360.0, "maximum": 360.0}, "levels: turn about the parent between consecutive children, in degrees.", LEVELS_DEFAULTS["rotate"]),
    "length_ratio": per_level({"type": "number", "exclusiveMinimum": 0, "maximum": 2.0}, "levels: child length over parent length (times the shape ratio on the trunk).", LEVELS_DEFAULTS["length_ratio"]),
    "curve": array({"type": "number", "minimum": -720.0, "maximum": 720.0}, f"levels: total bend of each stem towards its parent's direction, in degrees, per stem level from the trunk. Default {LEVELS_DEFAULTS['curve']}.", 1, MAX_LEVELS),
    "segments": array({"type": "integer", "minimum": 1, "maximum": 200}, f"levels: nodes along a stem besides those at children, per stem level from the trunk. Default {LEVELS_DEFAULTS['segments']}.", 1, MAX_LEVELS),
    "taper": number(f"levels: between branchings the radius falls along a stem as 1 - taper * (position along the stem). Default {LEVELS_DEFAULTS['taper']}.", 0.0, 0.95),
    "ratio_power": number(f"levels: a stem's tip radius is tip_radius * (stem length / trunk length) ^ ratio_power. Default {LEVELS_DEFAULTS['ratio_power']}.", 0.0, 3.0),
    "roots": ROOTS,
    "tip_radius": length("Radius at every tip (levels: at the trunk tip), in metres; the pipe model sums towards the base.", 0.01, maximum=1.0),
    "exponent": number("Pipe model exponent n in r^n = sum of the children's r^n; 2 is Leonardo's rule.", 1.8, 3.0, 2.0),
    "max_nodes": integer("Most nodes the skeleton may have, checked before growth.", 2, MAX_TREE_NODES, 20_000),
    "preview_resolution": integer("Bevel resolution of the preview curve.", 0, 8, 2),
    "offset": integer("First node of the page in the reply.", 0, MAX_TREE_NODES, 0),
    "limit": integer("Nodes in the page in the reply.", 0, MAX_QUERY_PAGE, DEFAULT_QUERY_PAGE),
}


def growth_report(grown):
    report = {key: value for key, value in grown.report.items() if key not in ("remaining", "kill")}
    if grown.trunk_nodes is not None:
        report["trunk_nodes"] = grown.trunk_nodes
    if grown.envelope is not None:
        report["envelope"] = grown.envelope.describe()
    return report


@command(
    "grow_tree",
    "Grow a tree skeleton by space colonisation in a crown or by recursive Weber-Penn levels, with roots and pipe-model radii; stores it on a preview curve and pages its nodes.",
    FIELDS,
    slow=True,
    family="natural",
    intents=(
        "grow a tree with branches and roots",
        "tree skeleton by space colonisation inside a crown shape",
        "conifer or broadleaf tree by recursive branch levels",
        "branch radii that thin by Leonardo's rule",
    ),
    nearest=(("curve_from_points", "for one curve through points you give"), ("scatter", "to place finished trees over terrain"), ("sweep", "to sweep one profile along a path")),
)
def grow_tree(ctx, args):
    require_free_name(args["name"])
    location = numpy.array(args["location"], dtype=float)
    skeleton, grown = grow(ctx, args, location)
    curve = preview_curve(args["name"], skeleton, args["preview_resolution"])
    preview = link_object(ctx, args["name"], curve)
    preview.location = location
    preview[PROPERTY] = skeleton.to_property()
    ctx.view_layer.update()
    return {"name": preview.name, "method": args["method"], "property": PROPERTY, "format": FORMAT, "version": VERSION, **skeleton.summary(), "growth": growth_report(grown), "page": skeleton.page(args["offset"], args["limit"])}


@command(
    "tree_skeleton",
    "Read the skeleton grown by grow_tree, or imported from glTF extras, as a summary and a page of nodes: position, parent, radius, order and kind.",
    {
        "name": string("Object that carries the skeleton."),
        "offset": integer("First node of the page.", 0, MAX_TREE_NODES, 0),
        "limit": integer("Nodes in the page.", 0, MAX_QUERY_PAGE, DEFAULT_QUERY_PAGE),
    },
    ["name"],
    mutates=False,
    family="natural",
    intents=("page through the nodes of a tree skeleton",),
    nearest=(("grow_tree", "to grow a new skeleton"), ("scene_info", "for object counts and bounds")),
)
def tree_skeleton(ctx, args):
    skeleton = from_property(get_object(args["name"]))
    return {"name": args["name"], "method": skeleton.method, "format": FORMAT, "version": VERSION, **skeleton.summary(), "page": skeleton.page(args["offset"], args["limit"])}
