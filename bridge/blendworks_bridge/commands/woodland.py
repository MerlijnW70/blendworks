"""The woodland command."""
import json

import bpy
import numpy

from .. import woodland_build as build
from ..errors import bad_args
from ..limits import (FRACTION, LEAST_LIOCOURT_Q, MAX_DENSITY_FACTOR, MAX_EDGE_ZONE, MAX_LIOCOURT_Q, MAX_RIM_WANDER,
                      MAX_SEED, MAX_STANDS, MAX_UNDERSTOREY_VARIANTS, MAX_WOODLAND_MEMORY, MAX_WOODLAND_PLANTS,
                      MAX_WOODLAND_TRIANGLES, MAX_WOODLAND_VARIANTS, QUARTER_TURN, WOODLAND_INSTANCE_BYTES,
                      WOODLAND_TRIANGLE_BYTES)
from ..limits_woodland import DEFAULT_WOODLAND_MEMORY, DEFAULT_WOODLAND_PLANTS, DEFAULT_WOODLAND_TRIANGLES
from ..registry import command
from ..schema import CREATES, EXISTS, array, boolean, described, integer, length, names, number, obj, ref, string
from ..tree_species import SHRUB_NAMES, TREE_NAMES
from ..util import get_object, require_free_name
from ..woodland_canopy import crown_rows, shade_ground, write_canopy
from ..woodland_edges import EDGE_DEFAULTS, KINDS, profile_table
from ..woodland_measure import measured
from ..woodland_plan import expected_class_shares, plan_woodland
from ..woodland_site import Site
from ..workers import MAX_WORKERS
from ..woodland_stands import STAND, footprints_of

DEFAULT_NAME = "Woodland"
DEFAULT_TREES = ["oak", "birch", "maple", "willow"]


def plan_woodland_names(args, state):
    name = args.get("name", DEFAULT_NAME)
    state.add("object", name)
    for layer in build.LAYER_NAMES:
        state.add("object", f"{name}_{layer}")


EDGE = described(obj({
    "fringe": length(f"Width in metres of the tall-herb fringe outside the rim. Default {EDGE_DEFAULTS['fringe']}.", maximum=MAX_EDGE_ZONE),
    "mantle": length(f"Width in metres of the shrub mantle inside the rim. Default {EDGE_DEFAULTS['mantle']}.", maximum=MAX_EDGE_ZONE),
    "transition": length(f"Width in metres of the sapling and young-tree zone behind the mantle. Default {EDGE_DEFAULTS['transition']}.", maximum=MAX_EDGE_ZONE),
}), "The edge zones from the open ground to the canopy.")

BUDGET = described(obj({
    "triangles": integer("Most triangles of all plant variants together (the unique meshes).", 1, MAX_WOODLAND_TRIANGLES, DEFAULT_WOODLAND_TRIANGLES),
    "plants": integer("Most instanced plants.", 1, MAX_WOODLAND_PLANTS, DEFAULT_WOODLAND_PLANTS),
    "memory": integer("Most bytes the plants may take: triangles times woodland_triangle_bytes plus plants times woodland_instance_bytes.", 1, MAX_WOODLAND_MEMORY, DEFAULT_WOODLAND_MEMORY),
}), "Budgets checked before any plant is grown and again after.")


@command(
    "woodland",
    "Trees in stands: copses, groves, hedgerows and forest edges with age classes, shrub mantles, herbs and ferns, grown as variants and instanced; writes canopy shade on the ground.",
    {
        "name": ref(string("Name of the woodland's group; its layers get suffixes.", default=DEFAULT_NAME), "object", CREATES),
        "ground": ref(names("Ground meshes the plants stand on; the canopy attribute is written on them."), "object", EXISTS),
        "stands": array(STAND, "The stands.", 1, MAX_STANDS),
        "species": array({"type": "string", "enum": list(TREE_NAMES)}, "Tree species to choose from by moisture and light.", 1, len(TREE_NAMES), DEFAULT_TREES),
        "shrubs": array({"type": "string", "enum": list(SHRUB_NAMES)}, "Shrub species of the mantle and the understorey.", 1, len(SHRUB_NAMES), list(SHRUB_NAMES)),
        "edge": EDGE,
        "q": number("de Liocourt quotient: each younger age class holds q times as many trees as the one above it.", LEAST_LIOCOURT_Q, MAX_LIOCOURT_Q, 1.6),
        "variants": integer("Grown variants per species and age class.", 1, MAX_WOODLAND_VARIANTS, 2),
        "understorey_variants": integer("Built variants of ferns and of herbs.", 1, MAX_UNDERSTOREY_VARIANTS, 6),
        "detail": string("full grows curled leaves and round twigs; low flat leaves, for far stands.", ["full", "low"], "full"),
        "points_share": number("Share of a species' attraction points or first branches the variants use.", None, FRACTION, 1.0, exclusive_minimum=0.0),
        "shrub_layer": boolean("Grow the shrub mantle and understorey shrubs.", True),
        "understorey": boolean("Place tall herbs in the fringe and ferns under the canopy.", True),
        "shrub_density": number("Factor on the shrub density.", 0.0, MAX_DENSITY_FACTOR, 1.0),
        "understorey_density": number("Factor on the density of herbs and ferns.", 0.0, MAX_DENSITY_FACTOR, 1.0),
        "max_slope": number("Steepest ground in degrees that carries plants.", 0.0, QUARTER_TURN, 35.0),
        "rim_wander": number("Metres by which a seeded noise moves each stand's rim in and out.", 0.0, MAX_RIM_WANDER, 3.0),
        "rim_wavelength": length("Wavelength in metres of the rim's wander.", 30.0),
        "canopy_attribute": string("Float point attribute written on the ground: the canopy cover over each vertex, 0 to 1.", default="meadow_canopy"),
        "shade_ground": boolean("Layer leaf litter and moss onto the ground's materials where the canopy closes.", True),
        "budget": BUDGET,
        "workers": integer("Most child sessions for growing the variants (grow_trees).", 1, MAX_WORKERS),
        "parallel": boolean("false grows every variant in this session.", True),
        "seed": integer("Seed of every stand, plant and variant.", 0, MAX_SEED, 0),
    },
    ["ground", "stands"],
    plan=plan_woodland_names,
    slow=True,
    family="natural",
    intents=("trees in copses, groves and hedgerows", "forest edge with shrubs and saplings", "woodland stand with understorey and ferns"),
    nearest=(("grow_trees", "for a list of single trees"), ("distant_forest", "for forest far from the camera"), ("scatter", "to place copies of one mesh")),
)
def woodland(ctx, args):
    name = args["name"]
    require_free_name(name)
    for layer in build.LAYER_NAMES:
        require_free_name(f"{name}_{layer}")
    if bpy.data.collections.get(f"{name}_variants") is not None:
        raise bad_args(f"a collection named {name}_variants already exists")
    ground = [get_object(entry) for entry in args["ground"]]
    for obj in ground:
        if obj.type != "MESH":
            raise bad_args(f"{obj.name} is not a mesh")
    edge = {**EDGE_DEFAULTS, **args.get("edge", {})}
    budget = {"triangles": DEFAULT_WOODLAND_TRIANGLES, "plants": DEFAULT_WOODLAND_PLANTS, "memory": DEFAULT_WOODLAND_MEMORY, **args.get("budget", {})}
    depsgraph = ctx.view_layer.depsgraph
    site = Site(ground, depsgraph, ctx.scene, args["max_slope"])
    footprints = footprints_of(args, site)
    settings = {"seed": args["seed"], "q": args["q"], "edge": edge, "shrubs": args["shrub_layer"], "understorey": args["understorey"],
                "shrub_density": args["shrub_density"], "understorey_density": args["understorey_density"]}
    plants, stands = plan_woodland([(footprint, species, shrubs) for footprint, species, shrubs, _ in footprints], site, settings)
    count = len(plants["xy"])
    if count > budget["plants"]:
        raise bad_args(f"the stands hold {count} plants, more than budget.plants {budget['plants']}; give smaller stands or lower the densities")
    understorey_count = args["understorey_variants"] if args["understorey"] else 0
    trees, shrubs, details, counts, estimate = build.fitted_plan(plants, args["variants"], understorey_count, budget, count, args["points_share"], args["detail"], memory_of)
    check_budget(estimate, count, budget, "estimated")
    group = bpy.data.objects.new(name, None)
    ctx.scene.collection.objects.link(group)
    root = build.hidden_collection(ctx, f"{name}_variants")
    collections = {layer: build.hidden_collection(ctx, f"{name}_{layer}_variants", root) for layer in build.LAYER_NAMES}
    grow = {"details": details, "points_share": args["points_share"], "parallel": args["parallel"], **({"workers": args["workers"]} if "workers" in args else {})}
    made = {}
    made["trees"], tree_report = build.grow_woody(ctx, name, trees, "trees", grow, args["seed"], collections["trees"])
    made["shrubs"], shrub_report = build.grow_woody(ctx, name, shrubs, "shrubs", grow, args["seed"] + 1, collections["shrubs"])
    made["herbs"] = build.build_understorey(ctx, name, "herbs", understorey_count, args["seed"], collections["herbs"]) if understorey_count else []
    made["ferns"] = build.build_understorey(ctx, name, "ferns", understorey_count, args["seed"] + 1, collections["ferns"]) if understorey_count else []
    unique = sum(build.triangles(objects) for objects in made.values())
    check_budget(unique, count, budget, "grown")
    heights, _ = site.surface(plants["xy"]) if count else (numpy.zeros(0), None)
    heights = numpy.nan_to_num(heights)
    layers = {}
    for index, layer in enumerate(build.LAYER_NAMES):
        chosen = numpy.flatnonzero(plants["layer"] == index)
        if layer in ("trees", "shrubs"):
            picks = build.variant_picks(plants, chosen, trees if layer == "trees" else shrubs)
            scales = build.woody_scales(plants, chosen)
        else:
            picks = build.understorey_picks(plants, chosen, max(len(made[layer]), 1))
            scales = plants["height"][chosen] / build.PLANT_SIZE[layer]
        instancer = build.instance_layer(ctx, name, layer, plants, chosen, picks, scales, heights, collections[layer], group) if len(made[layer]) else None
        layers[layer] = {"object": instancer.name if instancer else None, "count": int(len(chosen)) if instancer else 0, "variants": len(made[layer]),
                         "triangles": build.triangles(made[layer])}
    canopy = write_canopy(ground, crown_rows(plants, build.KLASS_NAMES), args["canopy_attribute"])
    shaded = shade_ground(ctx, ground, args["canopy_attribute"], args["seed"]) if args["shade_ground"] else []
    group["blendworks_woodland"] = json.dumps({"ground": [obj.name for obj in ground], "canopy_attribute": args["canopy_attribute"], "layers": {key: value["object"] for key, value in layers.items()}})
    ctx.view_layer.update()
    statistics = measured(plants, [(footprint, species, shrubs) for footprint, species, shrubs, _ in footprints], edge, args["seed"])
    return {
        "name": group.name,
        "stands": [{**stand, **extra} for stand, (_, _, _, extra) in zip(stands, footprints)],
        "layers": layers,
        "plants": count,
        "classes": statistics["classes"],
        "class_shares": {"measured": statistics["class_shares"], "expected": expected_class_shares(args["q"])},
        "regularity": [entry["regularity"] for entry in statistics["stands"]],
        "clustering": statistics["clustering"],
        "edge_profile": statistics["edge_profile"],
        "edge": {"zones": edge, "profiles": profile_table(edge, numpy.arange(-edge["fringe"] - 4.0, edge["mantle"] + edge["transition"] + 6.0, 2.0))},
        "species": {str(name): int((plants["species"] == name).sum()) for name in sorted({str(value) for value in plants["species"][plants["layer"] <= 1]})},
        "canopy": {"attribute": args["canopy_attribute"], "ground": canopy, "shaded_materials": shaded},
        "budget": {"triangles": unique, "estimated_triangles": estimate, "details": details, "variants": counts, "plants": count, "memory": memory_of(unique, count), "limits": budget},
        "growth": {"trees": tree_report, "shrubs": shrub_report},
        "kinds": sorted(KINDS),
    }


def memory_of(triangles, plants):
    return int(triangles * WOODLAND_TRIANGLE_BYTES + plants * WOODLAND_INSTANCE_BYTES)


def check_budget(triangles, plants, budget, stage):
    if triangles > budget["triangles"]:
        raise bad_args(f"the plant variants {stage} hold {triangles} triangles, more than budget.triangles {budget['triangles']}; lower variants, points_share or use detail low")
    memory = memory_of(triangles, plants)
    if memory > budget["memory"]:
        raise bad_args(f"the woodland {stage} takes {memory} bytes, more than budget.memory {budget['memory']}; lower variants or the stands")

