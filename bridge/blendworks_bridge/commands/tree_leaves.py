import bpy
import numpy

from ..errors import bad_args
from ..kit_limits import MAX_INSTANCES
from ..registry import command
from ..schema import boolean, described, integer, length, number, obj, string, validate, vector3
from ..tree_leaves import leaf_card, place_leaves
from ..tree_skeleton import from_property
from ..util import get_mesh_object, get_object
from .placement import place_copies

CARD = described(
    obj(
        {
            "width": number("Width of the built-in card as a share of its length.", 0.05, 2.0, 0.55),
            "fold": number("V-fold of the card along its midrib, in degrees.", 0.0, 60.0, 15.0),
        }
    ),
    "The built-in leaf card: a unit-length card along X with UVs on the unit square (midrib at u 0.5, tip at v 1), as the leaf preset expects.",
)

ALIGN = described(
    obj(
        {
            "sun": vector3("Direction towards the sun.", [0.0, 0.0, 1.0]),
            "factor": number("How far each leaf turns its face towards the sun about its own axis: 0 none, 1 fully.", 0.0, 1.0, 0.6),
        }
    ),
    "Sun-facing alignment.",
)

JITTER = described(
    obj(
        {
            "size": number("Size change, up to this share either way.", 0.0, 0.9, 0.2),
            "roll": number("Turn about the leaf axis, up to this many degrees either way.", 0.0, 180.0, 20.0),
        }
    ),
    "Seeded variation per leaf.",
)

FIELDS = {
    "name": string("Object that carries a tree skeleton: the grow_tree preview, the tree_mesh bark or an imported object."),
    "leaves_name": string("Name of the leaves object (or group of linked copies). Default name_leaves."),
    "source": string("Mesh object to use as the leaf (base at its origin, length along +X, face towards +Z); default the built-in card."),
    "card": CARD,
    "size": length("Leaf length in metres on the outermost twigs.", 0.12, maximum=10.0),
    "size_by_order": number("Size factor per branch order inward from the twigs.", 0.1, 2.0, 0.85),
    "density": number("Leaves per metre along the leafy branches.", 0.1, 500.0, 18.0),
    "orders": integer("How many branch orders, counted from the twigs inward, carry leaves (1: twigs only).", 1, 6, 2),
    "tip_leaves": integer("Extra leaves at every twig tip.", 0, 12, 3),
    "divergence": number("Turn about the twig between consecutive leaves, in degrees (phyllotaxis).", 0.0, 360.0, 137.5),
    "angle": number("Angle between a leaf and its twig, in degrees.", 0.0, 120.0, 55.0),
    "align": ALIGN,
    "jitter": JITTER,
    "seed": integer("Seed of the start phase and the jitter; the same seed gives the same leaves.", 0, 2**31 - 1, 0),
    "material": string("Material to put on the leaves, for example a leaf preset with cutout."),
    "realize": boolean("Merge the leaves into one mesh (for export) instead of linked copies.", True),
    "group": boolean("Parent linked copies to an empty named leaves_name.", True),
}

NESTED = ("card", "align", "jitter")


@command(
    "tree_leaves",
    "Place leaf cards or a given leaf on the twig tips and last branch orders of a tree skeleton, in phyllotaxis along each twig, sun-facing, seeded.",
    FIELDS,
    ["name"],
    slow=True,
    family="natural",
    intents=("leaves on the twigs of a tree", "foliage crown of leaf cards", "needle clusters on a conifer"),
    nearest=(("instances", "for copies at points you give"), ("scatter", "to scatter copies over a surface"), ("tree_mesh", "for the bark")),
)
def tree_leaves(ctx, args):
    for key in NESTED:
        if key not in args:
            args[key] = validate(FIELDS[key], {})
    source_object = get_object(args["name"])
    skeleton = from_property(source_object)
    name = args.get("leaves_name") or f"{source_object.name}_leaves"
    if numpy.linalg.norm(args["align"]["sun"]) == 0:
        raise bad_args("align.sun must not be zero")
    material = None
    if "material" in args:
        material = bpy.data.materials.get(args["material"])
        if material is None:
            raise bad_args(f"no material named {args['material']}; create it with material_procedural or add_material")
    leaves, matrices, sizes = place_leaves(skeleton, args)
    if len(matrices) > MAX_INSTANCES:
        raise bad_args(f"{len(matrices)} leaves; the cap is {MAX_INSTANCES}, so lower density, tip_leaves or orders")
    world = source_object.matrix_world
    placed = [world @ matrix for matrix in matrices]
    built = None
    if "source" in args:
        mesh = get_mesh_object(args["source"]).data
    else:
        built = bpy.data.meshes.new(f"{name}_card")
        leaf_card(args["card"]["width"], args["card"]["fold"]).to_mesh(built)
        mesh = built
    if material is not None and built is not None:
        built.materials.append(material)
    try:
        result = place_copies(ctx, {"name": name, "realize": args["realize"], "group": args["group"]}, mesh, placed)
    finally:
        if built is not None and args["realize"]:
            bpy.data.meshes.remove(built)
    if material is not None and args["realize"]:
        merged = bpy.data.objects[result["name"]].data
        merged.materials.clear()
        merged.materials.append(material)
    tips = sum(1 for leaf in leaves if leaf.tip)
    result.update({
        "leaves": len(leaves),
        "tip_leaves": tips,
        "twigs": len({leaf.chain for leaf in leaves}),
        "divergence": args["divergence"],
        "size_range": [round(min(sizes), 6), round(max(sizes), 6)] if sizes else None,
        "material": material.name if material is not None else None,
    })
    return result
