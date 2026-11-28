"""Tree planning: presets, defaults, envelopes and the grown result."""

import math

import numpy

from .errors import bad_args
from .kit_limits import MAX_TREE_POINTS
from .scatter_surface import read_surface
from .tree_colonize import ROOT, SHOOT, Colonization, Group, Nodes, grow_lead, unit
from .tree_form import Form, above_ground, form_active, reindex
from .tree_levels import LevelGrowth, LevelPlan
from .tree_presets import PRESETS
from .tree_radii import Taper, branch_orders, pipe_radii
from .tree_shapes import SHAPES, MeshEnvelope, RevolutionEnvelope
from .tree_skeleton import Skeleton
from .tree_strands import hem_keep
from .util import get_mesh_object

COLONIZATION_DEFAULTS = {"crown_radius": 3.0, "points": 3000, "influence": 1.2, "kill": 0.3, "step": 0.15, "tropism": [0.0, 0.0, 0.0]}
LEVELS_DEFAULTS = {
    "levels": 3,
    "branches": [36, 10, 4],
    "down_angle": [70.0, 45.0, 40.0],
    "rotate": [137.5],
    "length_ratio": [0.35, 0.4, 0.4],
    "curve": [0.0, 25.0, 15.0, 0.0],
    "curve_back": [0.0],
    "curve_variation": [0.0],
    "segments": [24, 8, 5, 3],
    "taper": 0.6,
    "ratio_power": 1.0,
    "length_variation": [0.0],
    "down_angle_variation": [0.0],
    "rotate_variation": [0.0],
    "spacing_variation": [0.0],
    "child_probability": [1.0],
    "whorl": [1],
    "rotate_offset": [0.0],
    "down_angle_top": None,
}
BASE_DEFAULTS = {"method": "colonization", "height": 8.0, "trunk_height": 2.0, "envelope": "spherical", "tip_radius": 0.01}
MERGED_FIELDS = ("gravitropism", "phototropism", "gnarl", "wind", "roots", "sway", "hem")
ROOT_TOP_SHARE = 0.02
UP = numpy.array([0.0, 0.0, 1.0])


def with_preset(args):
    preset = PRESETS[args.get("preset", "default")]
    if "method" in args and "method" in preset and args["method"] != preset["method"]:
        raise bad_args(f"preset {args['preset']} grows by method {preset['method']}; leave method out or pick another preset")
    settings = {**BASE_DEFAULTS, **preset}
    for name, value in args.items():
        settings[name] = {**preset[name], **value} if name in MERGED_FIELDS and name in preset else value
    return settings


def with_defaults(args):
    settings = with_preset(args)
    method = settings["method"]
    own, other = (COLONIZATION_DEFAULTS, LEVELS_DEFAULTS) if method == "colonization" else (LEVELS_DEFAULTS, COLONIZATION_DEFAULTS)
    stray = sorted(name for name in other if name in args)
    if stray:
        raise bad_args(f"{', '.join(stray)} {'applies' if len(stray) == 1 else 'apply'} to the other method; method {method} does not use {'it' if len(stray) == 1 else 'them'}")
    for name, value in own.items():
        settings.setdefault(name, value)
    return settings


def check_points(settings):
    crown = settings["points"] if settings["method"] == "colonization" else 0
    roots = settings["roots"]["points"] if "roots" in settings else 0
    if crown + roots > MAX_TREE_POINTS:
        raise bad_args(f"{crown + roots} attraction points are more than the cap of {MAX_TREE_POINTS}; lower points or roots.points")


def crown_envelope(ctx, settings, location):
    name = settings["envelope"]
    if name in SHAPES:
        if settings["height"] <= settings["trunk_height"]:
            raise bad_args("height, the top of the crown, must be above trunk_height, where the crown starts")
        return RevolutionEnvelope(name, settings["trunk_height"], settings["height"], settings["crown_radius"])
    surface = read_surface(get_mesh_object(name), ctx.depsgraph())
    return MeshEnvelope(name, surface.corners - location)


def soil_envelope(roots):
    return RevolutionEnvelope(roots["shape"], -roots["depth"], -ROOT_TOP_SHARE * roots["depth"], roots["radius"], widest_at_top=True)


def root_group(settings):
    roots = settings["roots"]
    envelope = soil_envelope(roots)
    points = envelope.sample(numpy.random.default_rng([settings["seed"], 1]), roots["points"])
    return Group(ROOT, points, envelope, roots["influence"], roots["kill"], roots["step"], roots["tropism"])


class Grown:
    def __init__(self, nodes, report, trunk_nodes, envelope, tips, taper=None, orders=None):
        self.nodes = nodes
        self.report = report
        self.trunk_nodes = trunk_nodes
        self.envelope = envelope
        self.tips = tips
        self.taper = taper
        self.orders = orders


def check_trunk(settings, step, max_nodes):
    trunk = int(math.ceil(settings["trunk_height"] / step)) + 1
    if trunk > max_nodes:
        raise bad_args(f"the trunk alone needs {trunk} nodes at step {step} m, more than max_nodes {max_nodes}")
    return trunk


def grow_colonization(ctx, settings, location):
    if settings["kill"] >= settings["influence"]:
        raise bad_args("kill must be smaller than influence, or every point dies before it can attract a node")
    envelope = crown_envelope(ctx, settings, location)
    points = envelope.sample(numpy.random.default_rng([settings["seed"], 0]), settings["points"])
    crown = Group(SHOOT, points, envelope, settings["influence"], settings["kill"], settings["step"], settings["tropism"])
    nodes = Nodes(settings["max_nodes"])
    nodes.add(numpy.zeros(3), -1, SHOOT)
    lean, _ = unit(UP + crown.tropism)
    if lean[2] <= 0.0:
        raise bad_args("the tropism points the trunk at or below the ground; give it a smaller sideways or downward part")
    steps = check_trunk(settings, crown.step, settings["max_nodes"]) - 1
    for _ in range(steps):
        nodes.add(nodes.positions[nodes.count - 1] + crown.step * lean, nodes.count - 1, SHOOT)
    grow_lead(nodes, crown, lean, envelope.bounds()[1][2])
    trunk_nodes = nodes.count
    groups = [crown] + ([root_group(settings)] if "roots" in settings else [])
    growth = Colonization(nodes, groups, 0.0).run()
    report = growth.report()
    report["remaining"] = [growth.remaining(index) for index in range(len(groups))]
    report["kill"] = [group.kill for group in groups]
    return Grown(nodes, report, trunk_nodes, envelope, None)


def grow_levels(settings):
    if settings["envelope"] not in SHAPES:
        raise bad_args(f"levels takes a built-in crown shape as envelope ({', '.join(SHAPES)}), not a mesh")
    plan = LevelPlan(settings)
    bound = plan.node_bound()
    if bound > settings["max_nodes"]:
        raise bad_args(f"a levels tree with these branches may need {bound} nodes, more than max_nodes {settings['max_nodes']}; lower branches, levels or segments, or raise max_nodes")
    nodes = Nodes(settings["max_nodes"])
    nodes.add(numpy.zeros(3), -1, SHOOT)
    growth = LevelGrowth(plan, nodes, 0.0).grow()
    report = {"stems": len(growth.stems), "truncated_stems": growth.truncated}
    if "roots" in settings:
        group = root_group(settings)
        roots = Colonization(nodes, [group], 0.0).run()
        report.update(roots.report())
        report["remaining"] = [roots.remaining(0)]
        report["kill"] = [group.kill]
    stem_of, fraction, preset, lengths = growth.stem_tables(nodes.count)
    return Grown(nodes, report, None, None, (stem_of, lengths, plan.length), Taper(stem_of, fraction, settings["taper"]), preset)


def tip_radii(settings, grown, kinds):
    tips = numpy.full(len(kinds), settings["tip_radius"])
    if grown.tips is not None:
        stem_of, lengths, trunk_length = grown.tips
        shoots = stem_of >= 0
        tips[shoots] = settings["tip_radius"] * (lengths[stem_of[shoots]] / trunk_length) ** settings["ratio_power"]
    if "roots" in settings:
        tips[kinds == ROOT] = settings["roots"].get("tip_radius", settings["tip_radius"])
    return tips


def shape(settings, grown, positions, parents, kinds, tips, radii, orders):
    form = Form(settings, settings["seed"], settings["height"])
    positions, report = form.apply(positions, parents, kinds, orders, radii)
    keep = above_ground(positions, parents, kinds)
    report["pruned"] = int((~keep).sum())
    if "hem" in settings:
        hemmed = keep & hem_keep(positions, parents, orders, kinds, settings["hem"], settings["seed"])
        report["hem_pruned"] = int((keep & ~hemmed).sum())
        keep = hemmed
    grown.report["form"] = report
    if keep.all():
        return positions, parents, kinds, radii, orders
    kept, parents = reindex(keep, parents)
    taper = Taper(grown.taper.stem_of[kept], grown.taper.fraction[kept], grown.taper.taper) if grown.taper is not None else None
    preset = grown.orders[kept] if grown.orders is not None else None
    radii = pipe_radii(parents, tips[kept], settings["exponent"], taper)
    return positions[kept], parents, kinds[kept], radii, branch_orders(parents, kinds[kept], radii, preset)


def grow(ctx, args, location):
    settings = with_defaults(args)
    check_points(settings)
    grown = grow_colonization(ctx, settings, location) if settings["method"] == "colonization" else grow_levels(settings)
    positions, parents, kinds = (array.copy() for array in grown.nodes.view())
    tips = tip_radii(settings, grown, kinds)
    radii = pipe_radii(parents, tips, settings["exponent"], grown.taper)
    orders = branch_orders(parents, kinds, radii, grown.orders)
    if form_active(settings):
        positions, parents, kinds, radii, orders = shape(settings, grown, positions, parents, kinds, tips, radii, orders)
    skeleton = Skeleton(positions, parents, radii, orders, kinds, settings["exponent"], settings["tip_radius"], settings["method"])
    return skeleton, grown
