import bpy
from mathutils import Matrix, Vector

from ..instancing import finish_placements
from ..kit_limits import DEFAULT_QUERY_PAGE, MAX_LSYSTEM_MODULES, MAX_QUERY_PAGE, MAX_TREE_NODES
from ..lsystem_plan import plan, word_reply
from ..lsystem_presets import preset_names
from ..registry import command
from ..schema import array, boolean, described, integer, length, number, obj, string, vector3
from ..tree_skeleton import FORMAT, PROPERTY, VERSION, preview_curve
from ..util import get_mesh_object, link_object, require_free_name
from .placement import place_copies

MAX_RULES = 64
MAX_ORGAN_VARIANTS = 4

ORGAN = obj(
    {
        "symbol": string("One letter other than F and f that the turtle does not draw; each occurrence in the final string puts one copy of the organ there.", max_length=1),
        "objects": array(string("Mesh object to copy: base at its origin, length along X, top side along Z."), "Meshes to copy. The turtle's colour index, raised by ' and set by '(c), picks the entry; the last entry serves higher indices.", 1, MAX_ORGAN_VARIANTS),
        "scale": number("Scale of every copy.", 0.001, 1000.0, 1.0),
        "scale_by_parameter": boolean("Multiply the scale by the first parameter of the module, for example the length l of B(l, w).", False),
    },
    ["symbol", "objects"],
)

CONSTANT = obj({"name": string("Name used in the rules.", max_length=32), "value": number("Its value.", -1e9, 1e9)}, ["name", "value"])

FIELDS = {
    "name": string("Name of the preview curve object that carries the skeleton.", default="Plant"),
    "preset": string("A grammar from the book (documented in docs/DESIGN.md); anything else you give overrides it.", preset_names()),
    "axiom": string("The starting string, such as F or A(1,10): letters, turtle symbols and [ ], with numbers in parentheses for parametric modules.", max_length=1024),
    "rules": array(
        string("One production: predecessor [: condition] -> successor [: probability]. Examples: F -> F[+F]F[-F]F; A(l,w) : w > 1 -> !(w)F(l)A(l*0.9,w*0.7); F -> F[+F]F : 0.5.", max_length=1024),
        "Productions, each written as text. Rules with the same predecessor and a probability make a stochastic choice (the probabilities add to 1). A symbol without a rule stays as it is. Replaces the preset's rules.",
        0,
        MAX_RULES,
    ),
    "constants": array(CONSTANT, "Named numbers for use in conditions and successors, like #define in the book. They add to the preset's constants and replace those of the same name.", 0, 64),
    "iterations": integer("Derivation steps n. Default 5, or the preset's.", 0, 100),
    "angle": number("Angle increment in degrees for + - & ^ \\ / without a parameter. Default 22.5, or the preset's.", 0.0, 360.0),
    "step": length("Length in metres of F and f without a parameter; F(a) draws a times this. Default 0.1, or the preset's.", maximum=100.0),
    "width": length("Width in metres of a segment of width 1; !(w) sets w times this. The radius of a segment is half. Default 0.01, or the preset's.", maximum=10.0),
    "width_ratio": number("Factor of ! without a parameter and of a new branch when branch_taper is on; 1/sqrt(2) follows Leonardo's postulate for two equal daughters [S1, page 57]. Default 0.7071, or the preset's.", 0.05, 1.0),
    "branch_taper": boolean("Every [ starts a branch of width_ratio times the width of the stem. Default true, or the preset's."),
    "tropism": described(
        obj(
            {
                "vector": vector3("Tropism vector T.", minimum=-100.0, maximum=100.0),
                "strength": number("Susceptibility e: after each F the turtle turns towards T by e times |H x T| radians [S1, section 2.1].", -100.0, 100.0, 0.0),
            },
            ["vector"],
        ),
        "Bending of the axes towards a direction, for example [0, 0, -1] to droop.",
    ),
    "organs": array(ORGAN, "Meshes placed at the turtle's frame (heading along X, up along Z) at each occurrence of a symbol, as linked copies grouped under an empty named name_symbol.", 0, 8),
    "location": vector3("Where the plant stands, in world metres.", [0.0, 0.0, 0.0]),
    "seed": integer("Seed of the random choices of stochastic rules.", 0, 2**31 - 1, 0),
    "max_length": integer("Most modules the string may have after any step; a step that would pass it is refused before it runs out of memory.", 1, MAX_LSYSTEM_MODULES, 100_000),
    "max_nodes": integer("Most skeleton nodes (F and f) the final string may draw, checked before the turtle runs.", 2, MAX_TREE_NODES, 20_000),
    "preview_resolution": integer("Bevel resolution of the preview curve.", 0, 8, 2),
    "offset": integer("First node of the page in the reply.", 0, MAX_TREE_NODES, 0),
    "limit": integer("Nodes in the page in the reply.", 0, MAX_QUERY_PAGE, DEFAULT_QUERY_PAGE),
}


def organ_placements(organs, entry):
    placements = []
    scales = []
    for organ in organs:
        rows = [[organ.heading[row], organ.left[row], organ.up[row], organ.position[row]] for row in range(3)]
        placements.append(Matrix(rows + [[0.0, 0.0, 0.0, 1.0]]))
        scales.append(entry["scale"] * (organ.scale if entry["scale_by_parameter"] else 1.0))
    return placements, scales


def place_organs(ctx, args, planned, preview):
    placed = {}
    for entry in args.get("organs", ()):
        organs = [organ for organ in planned.plant.organs if organ.symbol == entry["symbol"]]
        top = len(entry["objects"]) - 1
        for variant, name in enumerate(entry["objects"]):
            chosen = [organ for organ in organs if min(organ.colour, top) == variant]
            if not chosen:
                continue
            placements, scales = organ_placements(chosen, entry)
            matrices = finish_placements(placements, [0.0, 0.0, 0.0], 1.0, None, scales)
            group = f"{args['name']}_{entry['symbol']}" + (str(variant) if top else "")
            reply = place_copies(ctx, {"name": group, "group": True, "realize": False}, get_mesh_object(name).data, matrices)
            bpy.data.objects[reply["name"]].parent = preview
            placed[group] = reply["count"]
    return placed


@command(
    "lsystem",
    "Grow a plant from an L-system: rewrite an axiom by bracketed, stochastic or parametric rules, draw it with a 3D turtle into a skeleton, and place leaf and flower organs.",
    FIELDS,
    slow=True,
    family="natural",
    intents=(
        "grow a fern, herb, grass or flowering plant from an L-system grammar",
        "bracketed L-system with rules, an axiom and a turtle angle",
        "stochastic plant in several seeds that look like one species",
        "parametric L-system tree with leaves and flowers at the apices",
    ),
    nearest=(("grow_tree", "for a tree by crown colonisation or Weber-Penn levels"), ("instances", "to place leaves and petals by phyllotaxis or on a path"), ("sweep", "to sweep one profile along a path")),
)
def lsystem(ctx, args):
    require_free_name(args["name"])
    for entry in args.get("organs", ()):
        for name in entry["objects"]:
            get_mesh_object(name)
        require_free_name(f"{args['name']}_{entry['symbol']}")
    planned = plan(args)
    skeleton = planned.plant.skeleton
    curve = preview_curve(args["name"], skeleton, args["preview_resolution"])
    preview = link_object(ctx, args["name"], curve)
    preview.location = Vector(args["location"])
    preview[PROPERTY] = skeleton.to_property()
    ctx.view_layer.update()
    organs = place_organs(ctx, args, planned, preview)
    ctx.view_layer.update()
    text, cut = word_reply(planned.derivation)
    report = {
        "preset": args.get("preset"),
        "iterations": len(planned.derivation.lengths) - 1,
        "string_lengths": planned.derivation.lengths,
        "rules_applied": {str(index): count for index, count in sorted(planned.derivation.applications.items())},
        "word": text,
        "word_truncated": cut,
        **{key: value for key, value in planned.plant.stats.items() if key != "nodes"},
        "organ_symbols": planned.organ_counts,
        "organ_groups": organs,
    }
    return {"name": preview.name, "method": "lsystem", "property": PROPERTY, "format": FORMAT, "version": VERSION, **skeleton.summary(), "lsystem": report, "page": skeleton.page(args["offset"], args["limit"])}
