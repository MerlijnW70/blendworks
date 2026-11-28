"""Tree skeleton commands: grow_tree (space colonisation or levels) and tree_skeleton."""

import numpy

from ..kit_limits import DEFAULT_QUERY_PAGE, MAX_QUERY_PAGE, MAX_TREE_NODES, MAX_TREE_POINTS
from ..limits import (BEND_RATE, BRANCH_ORDERS, FRACTION, HALF_TURN, LENGTH_RATIO, MAX_RELIEF, MAX_SEED,
                      PAIR, PIPE_EXPONENT, PREVIEW_BEVEL_RESOLUTION, QUARTER_TURN, SIZE_EXPONENT, SMALLEST_PIPE_EXPONENT,
                      SPACING_JITTER, SPECIFIC_STIFFNESS, STEM_CHILDREN, STEM_LEVELS, STEM_SEGMENTS, TROPISM_WEIGHT, TURN,
                      VARIATION, WHORL_BRANCHES, WINDING)
from ..registry import command
from ..schema import CREATES, array, described, integer, length, number, obj, ref, string, vector3
from ..tree_form import DEFAULT_KINK_ANGLE, GNARL_DEFAULTS, WIND_DEFAULTS
from ..tree_plan import BASE_DEFAULTS, COLONIZATION_DEFAULTS, LEVELS_DEFAULTS, grow
from ..tree_presets import preset_names
from ..tree_shapes import SHAPES
from ..tree_skeleton import FORMAT, PROPERTY, VERSION, from_property, preview_curve
from ..tree_species import PRESET_SPECIES, SPECIES_NAMES, SPECIES_PROPERTY
from ..tree_habit import habit_statistics
from ..tree_strands import HEM_DEFAULTS, strand_statistics
from ..util import get_object, link_object, require_free_name

METHODS = ("colonization", "levels")
MAX_LEVELS = STEM_LEVELS


def per_level(item, description, default_note):
    return array(item, f"{description} One entry per level from the first branches outward; the last entry repeats for deeper levels. Default {default_note}.", 1, MAX_LEVELS)


def tropism(description, bound=TROPISM_WEIGHT):
    return array({"type": "number", "minimum": -bound, "maximum": bound}, description, 3, 3)


def by_order(description):
    return array({"type": "number", "minimum": 0.0, "maximum": FRACTION}, f"{description} One weight per branch order from the trunk (0); the last repeats. Default [1].", 1, BRANCH_ORDERS)


def response(target, extra=None):
    return obj(
        {
            **(extra or {}),
            "strength": number(f"Bend rate towards {target} in radians per metre at a tip of tip_radius: a segment of length l turns by strength * weight * (tip_radius / r)^thinness * l * sin(its angle to {target}), after ABOP 2.1. Default 0.", 0.0, BEND_RATE),
            "by_order": by_order("Weight of the bend per order; 0 keeps an order as grown."),
            "thinness": number("Exponent of tip_radius / r, with r the node's pipe-model radius, so thin branches bend more. Default 1.", 0.0, SIZE_EXPONENT),
        }
    )


GNARL = described(
    obj(
        {
            "amplitude": length("Largest sideways displacement of a node in metres, times by_order and (r / base radius)^radius_power.", maximum=MAX_RELIEF),
            "wavelength": length(f"Wavelength of the smooth noise in metres. Default {GNARL_DEFAULTS['wavelength']}."),
            "radius_power": number(f"Exponent of r / base radius in the amplitude. Default {GNARL_DEFAULTS['radius_power']}.", 0.0, SIZE_EXPONENT),
            "by_order": by_order("Weight of the displacement per order."),
        },
        ["amplitude"],
    ),
    "Seeded smooth noise that moves each shoot node perpendicular to its stem; a lateral moves with its parent node. Both methods.",
)

WIND = described(
    obj(
        {
            "vector": tropism("Wind direction; its length is the bend rate in radians per metre at the top, for a tip of tip_radius.", BEND_RATE),
            "profile": number(f"Exponent of the height share z / height in the bend rate; 0.3 is about the drag of a 1/7 power-law wind. Default {WIND_DEFAULTS['profile']}.", 0.0, SIZE_EXPONENT),
            "thinness": number(f"Exponent of tip_radius / r. Default {WIND_DEFAULTS['thinness']}.", 0.0, SIZE_EXPONENT),
        },
        ["vector"],
    ),
    "Prevailing wind: bends every shoot segment towards the wind at a rate that grows with height and thinness, so the trunk curves more the higher it gets and the crown streams downwind. Both methods.",
)


SWAY = described(
    obj(
        {
            "strength": number("Largest bend rate towards the axis's own sideways direction, in radians per metre; each axis draws its direction and a share of the rate from the seed.", 0.0, BEND_RATE),
            "by_order": by_order("Weight of the sway per order."),
        },
        ["strength"],
    ),
    "Seeded sideways lean per axis, applied like a tropism, so hanging strands do not all fall plumb. Both methods.",
)

HEM = described(
    obj(
        {
            "height": length(f"Height above the base where hanging strands at the crown rim end, in metres. Default {HEM_DEFAULTS['height']}.", maximum=MAX_RELIEF),
            "rise": number("How much higher the hem sits at the trunk than at the rim, in metres, rising as (1 - reach / spread)^2. Default 0.", 0.0, MAX_RELIEF),
            "variation": number("Seeded change of each strand's end height, up to this share either way. Default 0.", 0.0, FRACTION),
            "order": integer(f"Lowest branch order that is cut at the hem. Default {HEM_DEFAULTS['order']}.", 1, BRANCH_ORDERS),
        }
    ),
    "Cut hanging strands where they fall below a hem that follows the crown: low at the rim, higher towards the trunk, varied per strand.",
)

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
            "tip_radius": length("Radius at every root tip, in metres. Default: tip_radius."),
        }
    ),
    "Grow roots by space colonisation in a soil envelope below the trunk base, joined to the tree at its base node.",
)

FIELDS = {
    "name": ref(string("Name of the preview curve object that carries the skeleton.", default="Tree"), "object", CREATES),
    "preset": string("A tree form documented in docs/DESIGN.md: the species oak, birch, pine, willow, maple and olive (tree_mesh and tree_leaves then pick the species' bark, leaves and twigs), or the forms default, weeping_willow, gnarled_oak, windswept_coastal; any field you give replaces the preset's, and objects merge by field.", preset_names()),
    "method": string("colonization grows towards attraction points in a crown envelope (Runions et al. 2007); levels builds recursive stems (Weber and Penn 1995). Default colonization, or the preset's.", METHODS),
    "location": vector3("Where the trunk base stands, in world metres.", [0.0, 0.0, 0.0]),
    "seed": integer("Seed of the attraction points; the same seed and settings give the same skeleton whatever the face or point order.", 0, MAX_SEED, 0),
    "height": length(f"colonization: top of the crown above the base; levels: trunk length; metres. Default {BASE_DEFAULTS['height']}, or the preset's.", maximum=MAX_RELIEF),
    "trunk_height": number(f"colonization: trunk grown straight up before colonisation and bottom of a built-in crown; levels: bare trunk below the first branch; metres. Default {BASE_DEFAULTS['trunk_height']}, or the preset's.", 0.0, MAX_RELIEF),
    "envelope": string(f"Crown: a Weber-Penn shape ({', '.join(SHAPES)}) or, for colonization, the name of a closed mesh object. Default {BASE_DEFAULTS['envelope']}, or the preset's."),
    "crown_radius": length(f"colonization: largest radius of a built-in crown, in metres. Default {COLONIZATION_DEFAULTS['crown_radius']}."),
    "points": integer(f"colonization: attraction points N in the crown. Default {COLONIZATION_DEFAULTS['points']}.", 1, MAX_TREE_POINTS),
    "influence": length(f"colonization: radius of influence di, in metres; a point attracts only its nearest node within it. Default {COLONIZATION_DEFAULTS['influence']}."),
    "kill": length(f"colonization: kill distance dk, in metres; a point closer to a node is removed. Default {COLONIZATION_DEFAULTS['kill']}."),
    "step": length(f"colonization: growth step D, in metres. Default {COLONIZATION_DEFAULTS['step']}."),
    "tropism": tropism("colonization: tropism vector g added to each normalised growth direction; it also leans the trunk. Default [0, 0, 0]."),
    "levels": integer(f"levels: stem levels including the trunk. Default {LEVELS_DEFAULTS['levels']}.", 1, MAX_LEVELS),
    "branches": per_level({"type": "integer", "minimum": 0, "maximum": STEM_CHILDREN}, "levels: children per stem; deeper stems get fewer when they are shorter.", LEVELS_DEFAULTS["branches"]),
    "down_angle": per_level({"type": "number", "minimum": 0.0, "maximum": HALF_TURN}, "levels: angle between a child and its parent, in degrees.", LEVELS_DEFAULTS["down_angle"]),
    "rotate": per_level({"type": "number", "minimum": -TURN, "maximum": TURN}, "levels: turn about the parent between consecutive children, in degrees.", LEVELS_DEFAULTS["rotate"]),
    "length_ratio": per_level({"type": "number", "exclusiveMinimum": 0, "maximum": LENGTH_RATIO}, "levels: child length over parent length (times the shape ratio on the trunk).", LEVELS_DEFAULTS["length_ratio"]),
    "curve": array({"type": "number", "minimum": -WINDING, "maximum": WINDING}, f"levels: total bend of each stem towards its parent's direction, in degrees, per stem level from the trunk. Default {LEVELS_DEFAULTS['curve']}.", 1, MAX_LEVELS),
    "curve_back": array({"type": "number", "minimum": -WINDING, "maximum": WINDING}, "levels: Weber-Penn CurveBack per stem level; when not 0 the first half of a stem bends by curve and the second half by curve_back, an S-bend when their signs differ. Default [0].", 1, MAX_LEVELS),
    "curve_variation": array({"type": "number", "minimum": 0.0, "maximum": WINDING}, "levels: Weber-Penn CurveV per stem level; each segment adds a seeded uniform bend within +-curve_variation * segment length / stem length degrees. Default [0].", 1, MAX_LEVELS),
    "length_variation": per_level({"type": "number", "minimum": 0.0, "maximum": VARIATION}, "levels: Weber-Penn LengthV; each child's length is scaled by 1 + u * variation with u seeded in [-1, 1].", "[0]"),
    "down_angle_variation": per_level({"type": "number", "minimum": 0.0, "maximum": QUARTER_TURN}, "levels: Weber-Penn DownAngleV; each child's down angle changes by up to this many degrees.", "[0]"),
    "rotate_variation": per_level({"type": "number", "minimum": 0.0, "maximum": HALF_TURN}, "levels: Weber-Penn RotateV; each child's azimuth changes by up to this many degrees.", "[0]"),
    "spacing_variation": per_level({"type": "number", "minimum": 0.0, "maximum": SPACING_JITTER}, "levels: each child moves along its parent by up to this share of the even spacing, so children are not evenly spaced.", "[0]"),
    "down_angle_top": per_level({"type": "number", "minimum": 0.0, "maximum": HALF_TURN}, "levels: down angle of the children at the tip of their parent (on the trunk, at its top), in degrees; it changes linearly from down_angle at the lowest child, so a pine's lower branches can stand level or droop while the upper ones rise.", "down_angle"),
    "rotate_offset": per_level({"type": "number", "minimum": -TURN, "maximum": TURN}, "levels: azimuth of the first child, in degrees from the side of the parent that faces the parent's own parent; with rotate 180, an offset of 90 sets alternate children left and right, the flat sprays of a pine or fir branch.", "[0]"),
    "whorl": per_level({"type": "integer", "minimum": 1, "maximum": WHORL_BRANCHES}, "levels: children grown at the same height around the parent, as in the whorls of a pine or fir; the rotate angle then turns each whorl against the one below it.", "[1]"),
    "child_probability": per_level({"type": "number", "minimum": 0.0, "maximum": FRACTION}, "levels: chance that each child is grown, so branching is occasional.", "[1]"),
    "segments": array({"type": "integer", "minimum": 1, "maximum": STEM_SEGMENTS}, f"levels: nodes along a stem besides those at children, per stem level from the trunk. Default {LEVELS_DEFAULTS['segments']}.", 1, MAX_LEVELS),
    "taper": number(f"levels: between branchings the radius falls along a stem as 1 - taper * (position along the stem). Default {LEVELS_DEFAULTS['taper']}.", 0.0, VARIATION),
    "ratio_power": number(f"levels: a stem's tip radius is tip_radius * (stem length / trunk length) ^ ratio_power. Default {LEVELS_DEFAULTS['ratio_power']}.", 0.0, SIZE_EXPONENT),
    "gravitropism": described(response("-Z"), "Bends shoots down after growth, more for higher orders and thinner branches, so long thin branches droop or weep while the trunk stays up. Both methods."),
    "phototropism": described(response("direction", {"direction": tropism("Direction of the light. Default [0, 0, 1].")}), "Bends shoots towards a light direction after growth, by order and thinness. Both methods."),
    "stiffness": length("Specific stiffness E / (rho g) of the wood in metres (green wood about 1e6); each segment sags by the cantilever curvature 4 W a / (stiffness r^4), W the r^2-weighted length beyond it and a the horizontal arm of its centre. Omit for no sag.", maximum=SPECIFIC_STIFFNESS),
    "gnarl": GNARL,
    "twist": number("Roll of the branching frame about each trunk segment, in degrees per metre: successive laterals leave the trunk turned by twist times their spacing, and a curved trunk winds into a helix. Default 0.", -TURN, TURN),
    "kink_probability": number("Chance that a shoot node, other than the first above the base, turns its stem abruptly by kink_angle about a seeded axis. Default 0.", 0.0, FRACTION),
    "kink_angle": number(f"Angle of a kink in degrees. Default {DEFAULT_KINK_ANGLE}.", 0.0, QUARTER_TURN),
    "wind": WIND,
    "sway": SWAY,
    "hem": HEM,
    "roots": ROOTS,
    "tip_radius": length(f"Radius at every tip (levels: at the trunk tip), in metres; the pipe model sums towards the base. Default {BASE_DEFAULTS['tip_radius']}, or the preset's."),
    "exponent": number("Pipe model exponent n in r^n = sum of the children's r^n; 2 is Leonardo's rule.", SMALLEST_PIPE_EXPONENT, PIPE_EXPONENT, 2.0),
    "max_nodes": integer("Most nodes the skeleton may have, checked before growth.", PAIR, MAX_TREE_NODES, 20_000),
    "preview_resolution": integer("Bevel resolution of the preview curve.", 0, PREVIEW_BEVEL_RESOLUTION, 2),
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
    "Grow a tree skeleton by space colonisation or Weber-Penn levels, with roots and pipe-model radii, weeping, gnarled or wind-bent; stores it on a preview curve and pages its nodes.",
    FIELDS,
    slow=True,
    family="natural",
    intents=(
        "grow a tree with branches and roots",
        "tree skeleton by space colonisation inside a crown shape",
        "conifer or broadleaf tree by recursive branch levels",
        "branch radii that thin by Leonardo's rule",
        "weeping willow, gnarled old oak or tree bent by the sea wind",
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
    preset = args.get("preset", "default")
    species = preset if preset in SPECIES_NAMES else PRESET_SPECIES.get(preset)
    if species:
        preview[SPECIES_PROPERTY] = species
    ctx.view_layer.update()
    return {"name": preview.name, "method": skeleton.method, "preset": preset, "species": species, "property": PROPERTY, "format": FORMAT, "version": VERSION, **skeleton.summary(), "growth": {**growth_report(grown), "strands": strand_statistics(skeleton), "habit": habit_statistics(skeleton)}, "page": skeleton.page(args["offset"], args["limit"])}


@command(
    "tree_skeleton",
    "Read the skeleton grown by grow_tree, or imported from glTF extras, as a summary and a page of nodes: position, parent, radius, order and kind.",
    {
        "name": ref(string("Object that carries the skeleton."), "object"),
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
