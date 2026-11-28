"""The tree_leaves command: foliage clusters or single leaves on a tree skeleton."""

import bpy
import numpy

from ..errors import bad_args
from ..kit_limits import MAX_INSTANCES
from ..limits import (ASPECT_RATIO, FEWEST_LEAVES_PER_METRE, BRANCH_ORDERS, CLUSTER_LEAVES, CLUSTER_VARIANTS, FRACTION, HALF_TURN, HUE_SHIFT,
                      LEAF_SHAPES, LEAST_CARD_WIDTH, LENGTH_RATIO, LINEAR_DENSITY, MAX_LENGTH, MAX_SCALE_FACTOR,
                      MAX_SEED, QUARTER_TURN, SHORTEST_LEAF_SHAPE, SHORTEST_SIDE_TWIG, SMALLEST_SIZE_STEP, SPRAY_FORKS, TIP_LEAVES, TIP_SPRAYS, TURN,
                      VARIATION as SHARE_EITHER_WAY)
from ..registry import command
from ..schema import CREATES, array, boolean, described, integer, length, number, obj, ref, string, vector3
from ..tree_canopy import leaf_area_report, linked, realized, variation_report
from ..tree_crown import crown_report
from ..tree_foliage import place_sprays
from ..tree_leaves import leaf_card, place_leaves
from ..tree_skeleton import from_property
from ..tree_species import FOLIAGE_DEFAULTS as DEFAULTS, LEAF_MATERIALS, SPECIES_NAMES, foliage_settings, species_material, species_of
from ..tree_sprays import ARRANGEMENTS, SprayStyle
from ..util import get_mesh_object, get_object
from .placement import place_copies

CLUSTER_DEFAULTS = DEFAULTS["clusters"]
VARIATION_DEFAULTS = DEFAULTS["variation"]

CARD = described(
    obj(
        {
            "width": number(f"Width of the leaf card as a share of its length. Default {DEFAULTS['card']['width']}, or the species'.", LEAST_CARD_WIDTH, ASPECT_RATIO),
            "fold": number(f"V-fold of the card along its midrib, in degrees. Default {DEFAULTS['card']['fold']}.", 0.0, QUARTER_TURN),
        }
    ),
    "The leaf card: a card along X with UVs on the unit square (midrib at u 0.5, tip at v 1), as the leaf preset expects.",
)

ALIGN = described(
    obj(
        {
            "sun": vector3("Direction towards the sun. Default [0, 0, 1]."),
            "factor": number(f"How far the outermost leaves turn their face towards the sun about their own axis: 0 none, 1 fully. Default {DEFAULTS['align']['factor']}.", 0.0, FRACTION),
            "inner": number(f"clusters: the same for the innermost, shaded clusters; the turn grows from inner to factor with the distance from the crown centre. Default {DEFAULTS['align']['inner']}.", 0.0, FRACTION),
        }
    ),
    "Sun-facing alignment, stronger for outer leaves.",
)

JITTER = described(
    obj(
        {
            "size": number(f"Size change of a leaf (single) or cluster, up to this share either way. Default {DEFAULTS['jitter']['size']}.", 0.0, SHARE_EITHER_WAY),
            "roll": number(f"Turn about the leaf or cluster axis, up to this many degrees either way. Default {DEFAULTS['jitter']['roll']}.", 0.0, HALF_TURN),
        }
    ),
    "Seeded variation per leaf (single) or per cluster.",
)

CLUSTERS = described(
    obj(
        {
            "arrangement": string(f"How leaves sit on a cluster's twig: alternate, opposite (pairs), terminal (a rosette at the tip, as on oak) or needles (bunches of needles fanning out of the twig). Default {CLUSTER_DEFAULTS['arrangement']}.", ARRANGEMENTS),
            "leaves": array({"type": "integer", "minimum": 1, "maximum": CLUSTER_LEAVES}, f"Fewest and most leaves on one cluster. Default {CLUSTER_DEFAULTS['leaves']}.", 2, 2),
            "spacing": number(f"Distance between clusters along the leafy branches, in metres; 0 puts clusters only at the tips. Default {CLUSTER_DEFAULTS['spacing']}.", 0.0, MAX_LENGTH),
            "spacing_variation": number(f"Change of each spacing, up to this share either way. Default {CLUSTER_DEFAULTS['spacing_variation']}.", 0.0, SHARE_EITHER_WAY),
            "per_tip": integer(f"Clusters fanning out of every skeleton tip, the twig level beyond the skeleton. Default {CLUSTER_DEFAULTS['per_tip']}.", 0, TIP_SPRAYS),
            "tip_spread": number(f"Angle between the tip clusters and the twig, in degrees. Default {CLUSTER_DEFAULTS['tip_spread']}.", 0.0, QUARTER_TURN),
            "angle": number(f"Angle between a cluster and its branch, in degrees. Default {CLUSTER_DEFAULTS['angle']}.", 0.0, HALF_TURN),
            "divergence": number(f"Turn about the branch between consecutive clusters, in degrees. Default {CLUSTER_DEFAULTS['divergence']}.", 0.0, TURN),
            "twig_length": length(f"Length of a cluster's twig in metres. Default {CLUSTER_DEFAULTS['twig_length']}."),
            "twig_radius": length(f"Radius of a cluster's twig at its base in metres. Default {CLUSTER_DEFAULTS['twig_radius']}."),
            "twig_bend": number(f"Upward (positive) or downward bend of a cluster's twig, as a height share of its length. Default {CLUSTER_DEFAULTS['twig_bend']}.", -FRACTION, FRACTION),
            "forks": array({"type": "integer", "minimum": 0, "maximum": SPRAY_FORKS}, f"Fewest and most side twigs on one cluster, each with its own leaves, so a cluster is a small branched spray. Default {CLUSTER_DEFAULTS['forks']}.", 2, 2),
            "fork_angle": number(f"Angle between a side twig and the cluster's twig, in degrees. Default {CLUSTER_DEFAULTS['fork_angle']}.", 0.0, QUARTER_TURN),
            "fork_length": number(f"Length of a side twig as a share of the cluster's twig. Default {CLUSTER_DEFAULTS['fork_length']}.", SHORTEST_SIDE_TWIG, LENGTH_RATIO),
            "leaf_angle": number(f"Angle between a leaf and the cluster's twig, in degrees. Default {CLUSTER_DEFAULTS['leaf_angle']}.", 0.0, HALF_TURN),
            "petiole": number(f"Share of the card taken by the leaf stalk; the leaf preset draws the stalk there. Default {CLUSTER_DEFAULTS['petiole']}.", 0.0, FRACTION),
            "droop": number(f"How far clusters hang towards the ground: 0 not at all, 1 straight down (willow). Default {CLUSTER_DEFAULTS['droop']}.", 0.0, FRACTION),
            "inner_keep": number(f"Share of the innermost clusters kept; shaded inner clusters are thinned and outer ones kept, giving the crown a leafy shell with depth. Default {CLUSTER_DEFAULTS['inner_keep']}.", 0.0, FRACTION),
            "bearing_radius": length(f"Twigs and branches thinner than this radius, in metres, carry clusters along their whole length, however many orders they are from the tips, so no bare thin sticks reach out of the foliage; 0 limits clusters to the last orders. Default {CLUSTER_DEFAULTS['bearing_radius']}."),
            "reach": number(f"Only the last this many metres of each leafy shoot carry clusters, the needles of the last few years on a conifer, so the inner branches stand bare and the foliage gathers in tufts at the branch ends; 0 covers the whole shoot. Default {CLUSTER_DEFAULTS['reach']}.", 0.0, MAX_LENGTH),
            "shade_growth": number(f"How much larger the innermost clusters' leaves are than the outermost (shade leaves are larger). Default {CLUSTER_DEFAULTS['shade_growth']}.", 0.0, FRACTION),
        }
    ),
    "Leaf clusters: small twigs that each carry several leaves, along the last orders and fanning out of every tip. Defaults come from the species, or the values named here.",
)

VARIATION = described(
    obj(
        {
            "size": number(f"Leaf size change within a cluster, up to this share either way. Default {VARIATION_DEFAULTS['size']}.", 0.0, SHARE_EITHER_WAY),
            "curl": number(f"Largest curl of a leaf along its length, in degrees. Default {VARIATION_DEFAULTS['curl']}.", 0.0, HALF_TURN),
            "fold": number(f"Change of the midrib fold, up to this many degrees either way. Default {VARIATION_DEFAULTS['fold']}.", 0.0, QUARTER_TURN),
            "tilt": number(f"Turn of each leaf about its own axis, up to this many degrees either way. Default {VARIATION_DEFAULTS['tilt']}.", 0.0, QUARTER_TURN),
            "hue": number(f"Hue change, up to this share of the colour circle either way (attribute leaf_hue). Default {VARIATION_DEFAULTS['hue']}.", 0.0, HUE_SHIFT),
            "saturation": number(f"Saturation change, up to this share either way (leaf_saturation). Default {VARIATION_DEFAULTS['saturation']}.", 0.0, SHARE_EITHER_WAY),
            "value": number(f"Brightness change, up to this share either way, darker inside the crown (leaf_value). Default {VARIATION_DEFAULTS['value']}.", 0.0, SHARE_EITHER_WAY),
            "age": number(f"Spread of leaf age from young (-1, paler, at the twig tips) to old (1, darker, near the base) (leaf_age). Default {VARIATION_DEFAULTS['age']}.", 0.0, FRACTION),
            "damage": number(f"Largest damage of the damaged leaves: brown margins, spots and holes (leaf_damage). Default {VARIATION_DEFAULTS['damage']}.", 0.0, FRACTION),
        }
    ),
    "Seeded per-leaf variation of the clusters; the colour, age, damage and shape values are face attributes that the leaf preset reads.",
)

FIELDS = {
    "name": ref(string("Object that carries a tree skeleton: the grow_tree preview, the tree_mesh bark or an imported object."), "object"),
    "leaves_name": ref(string("Name of the leaves object (or group of linked copies). Default name_leaves."), "object", CREATES),
    "species": string("Leaf, twig and colour settings of a species preset; default the species the tree was grown as (grow_tree preset), if any.", SPECIES_NAMES),
    "layout": string("clusters: leaf clusters on small twigs, with per-leaf variation (the default); single: one leaf per place in phyllotaxis along the twigs.", ["clusters", "single"]),
    "source": ref(string("Mesh object to use as the leaf (base at its origin, length along +X, face towards +Z); single layout only. Default the built-in card."), "object"),
    "card": CARD,
    "size": length(f"Leaf length in metres on the outermost twigs. Default {DEFAULTS['size']}, or the species'."),
    "size_by_order": number(f"Size factor per branch order inward from the twigs. Default {DEFAULTS['size_by_order']}.", SMALLEST_SIZE_STEP, MAX_SCALE_FACTOR),
    "density": number(f"single: leaves per metre along the leafy branches. Default {DEFAULTS['density']}.", FEWEST_LEAVES_PER_METRE, LINEAR_DENSITY),
    "orders": integer(f"How many branch orders, counted from the twigs inward, carry leaves (1: twigs only). Default {DEFAULTS['orders']}.", 1, BRANCH_ORDERS),
    "tip_leaves": integer(f"single: extra leaves at every twig tip. Default {DEFAULTS['tip_leaves']}.", 0, TIP_LEAVES),
    "divergence": number(f"single: turn about the twig between consecutive leaves, in degrees (phyllotaxis). Default {DEFAULTS['divergence']}.", 0.0, TURN),
    "angle": number(f"single: angle between a leaf and its twig, in degrees. Default {DEFAULTS['angle']}.", 0.0, HALF_TURN),
    "align": ALIGN,
    "jitter": JITTER,
    "clusters": CLUSTERS,
    "variation": VARIATION,
    "shape_length": array({"type": "number", "minimum": SHORTEST_LEAF_SHAPE, "maximum": MAX_SCALE_FACTOR}, f"clusters: length factor of the first, middle and last third of the leaf shapes, so the shapes differ in length as well as outline. Default {DEFAULTS['shape_length']}.", 3, 3),
    "shapes": integer(f"clusters: leaf shapes per species, drawn per leaf (attribute leaf_shape). Default {DEFAULTS['shapes']}.", 1, LEAF_SHAPES),
    "detail": string("clusters: full builds curled, folded leaves and round twigs; low builds flat two-triangle leaves and crossed twig cards for distant LODs.", ["full", "low"]),
    "variants": integer(f"clusters with realize false: distinct cluster meshes shared by the linked copies. Default {DEFAULTS['variants']}.", 1, CLUSTER_VARIANTS),
    "seed": integer("Seed of the placement and every variation; the same seed gives the same leaves.", 0, MAX_SEED, 0),
    "material": ref(string("Material for the leaves. Default the species leaf preset, or a leaf preset named leaf, created when missing."), "material"),
    "twig_material": ref(string("clusters: material for the cluster twigs. Default the first material of name (the bark), or bark."), "material"),
    "realize": boolean("Merge the leaves into one mesh (for export) instead of linked copies.", True),
    "group": boolean("Parent linked copies to an empty named leaves_name.", True),
    "measure": boolean("Render the crown from the judge's four side views and report crown.fill, the share of the crown silhouette that leaves, twigs and bark cover.", False),
}

SETTINGS_EXCLUDED = ("name", "seed", "realize", "group", "measure")


def leaf_material(ctx, args, species):
    if "material" in args:
        material = bpy.data.materials.get(args["material"])
        if material is None:
            raise bad_args(f"no material named {args['material']}; create it with material_procedural or add_material")
        return material
    return species_material(ctx, "leaf", species, f"{species}_leaf" if species else "leaf")


def twig_material(ctx, args, source_object, species):
    if "twig_material" in args:
        material = bpy.data.materials.get(args["twig_material"])
        if material is None:
            raise bad_args(f"no material named {args['twig_material']}")
        return material
    if source_object.type == "MESH" and source_object.data.materials and source_object.data.materials[0] is not None:
        return source_object.data.materials[0]
    return species_material(ctx, "bark", species, f"{species}_bark" if species else "bark")


def single_leaves(ctx, args, skeleton, source_object, name, material):
    leaves, matrices, sizes = place_leaves(skeleton, args)
    world = source_object.matrix_world
    placed = [world @ matrix for matrix in matrices]
    built = None
    if "source" in args:
        mesh = get_mesh_object(args["source"]).data
    else:
        built = bpy.data.meshes.new(f"{name}_card")
        leaf_card(args["card"]["width"], args["card"]["fold"]).to_mesh(built)
        built.materials.append(material)
        mesh = built
    try:
        result = place_copies(ctx, {"name": name, "realize": args["realize"], "group": args["group"]}, mesh, placed)
    finally:
        if built is not None and args["realize"]:
            bpy.data.meshes.remove(built)
    if args["realize"]:
        merged = bpy.data.objects[result["name"]].data
        merged.materials.clear()
        merged.materials.append(material)
    result.update({
        "leaves": len(leaves),
        "tip_leaves": sum(1 for leaf in leaves if leaf.tip),
        "twigs": len({leaf.chain for leaf in leaves}),
        "divergence": args["divergence"],
        "size_range": [round(min(sizes), 6), round(max(sizes), 6)] if sizes else None,
    })
    return result


def cluster_leaves(ctx, args, skeleton, source_object, name, material, twigs, species):
    if "source" in args:
        raise bad_args("source works with layout single; clusters build their own leaves")
    sprays = place_sprays(skeleton, args)
    if not sprays:
        raise bad_args("no leafy branch or tip to put clusters on")
    if len(sprays) > MAX_INSTANCES:
        raise bad_args(f"{len(sprays)} leaf clusters; the cap is {MAX_INSTANCES} instances, so raise clusters.spacing or lower per_tip or orders")
    style = SprayStyle(args)
    if args["realize"]:
        made, built, attributes, matrices = realized(ctx, name, style, args, sprays, material, twigs)
        made.matrix_world = source_object.matrix_world.copy()
        shape = LEAF_MATERIALS.get(species, {}).get("shape")
        report = {"name": made.name, "realized": True, "triangles": len(made.data.polygons), "variation": variation_report(built, attributes, matrices), "foliage": leaf_area_report(built, matrices, args["card"]["width"], shape)}
        leaves = built.count
    else:
        parent, leaves, variants = linked(ctx, name, style, args, sprays, material, twigs, source_object.matrix_world)
        report = {"name": parent.name if parent is not None else name, "realized": False, "variants": [mesh.name for mesh in variants], "triangles_per_cluster": round(float(numpy.mean([len(mesh.polygons) for mesh in variants])), 1)}
    ctx.view_layer.update()
    report.update({"count": len(sprays), "clusters": len(sprays), "leaves": leaves, "tip_clusters": sum(1 for spray in sprays if spray.tip), "twig_material": twigs.name})
    return report


def plan_tree_leaves(args, state):
    """The leaves object defaults to name_leaves; linked copies take names from the skeleton, and the default
    materials follow the tree's species, which only the scene knows."""
    leaves = args.get("leaves_name") or f"{args['name']}_leaves"
    state.add("object", leaves)
    if not args["realize"]:
        if not args["group"]:
            state.remove("object", leaves)
        state.unknown(("object",))
    if "material" not in args:
        if "species" in args:
            state.add("material", f"{args['species']}_leaf")
        else:
            state.unknown(("material",))
    if "twig_material" not in args and args.get("layout") != "single":
        state.unknown(("material",))


@command(
    "tree_leaves",
    "Foliage on a tree skeleton: leaf clusters on small twigs beyond every tip, per-leaf size, colour, age, damage, curl and shape, sun-facing outer leaves, species presets.",
    FIELDS,
    ["name"],
    slow=True,
    family="natural",
    intents=("leaves on the twigs of a tree", "foliage crown of leaf cards", "needle clusters on a conifer", "dense realistic crown of oak, birch, maple, olive or willow leaves"),
    nearest=(("instances", "for copies at points you give"), ("scatter", "to scatter copies over a surface"), ("tree_mesh", "for the bark")),
    plan=plan_tree_leaves,
)
def tree_leaves(ctx, args):
    source_object = get_object(args["name"])
    skeleton = from_property(source_object)
    species = args.get("species") or species_of(source_object)
    given = {key: value for key, value in args.items() if key not in SETTINGS_EXCLUDED}
    args = {**args, **foliage_settings(species, given)}
    name = args.get("leaves_name") or f"{source_object.name}_leaves"
    if numpy.linalg.norm(args["align"]["sun"]) == 0:
        raise bad_args("align.sun must not be zero")
    for key in ("leaves", "forks"):
        if args["clusters"][key][0] > args["clusters"][key][1]:
            raise bad_args(f"clusters.{key} is [fewest, most]; the first must not exceed the second")
    material = leaf_material(ctx, args, species)
    if args["layout"] == "single":
        result = single_leaves(ctx, args, skeleton, source_object, name, material)
    else:
        result = cluster_leaves(ctx, args, skeleton, source_object, name, material, twig_material(ctx, args, source_object, species), species)
    result.update({"layout": args["layout"], "species": species, "material": material.name})
    if args["measure"]:
        result["crown"] = crown_report(ctx, [source_object.name, result["name"]], material)
    return result
