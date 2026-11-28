"""The shore_stones command: stones clustered along a water line."""

import bpy
import numpy

from .. import liquid_grid, liquid_masks, liquid_world, stone_plan, stone_shape
from ..copies import realized_copy
from ..errors import bad_args
from ..kit_limits import MAX_INSTANCES
from ..limits import (BASE_NAME_LENGTH, FRACTION, LEAST_STONE_SIZE, MAX_RELIEF, MAX_SEED, MAX_STONE_CLASSES, MAX_STONE_GROUP_DENSITY,
                      MAX_STONE_SIZE, MAX_STONE_VARIANTS, MAX_STONES_PER_GROUP, POWER_EXPONENT, QUARTER_TURN)
from ..registry import command
from ..scatter_sizes import DISTRIBUTIONS
from ..scatter_surface import read_surface
from ..schema import CREATES, EXISTS, array, integer, length, number, ref, string
from ..util import get_mesh_object, mesh_counts, require_free_name

DISTRIBUTIONS_HERE = tuple(name for name in DISTRIBUTIONS if name != "uniform")
STONE_MATERIAL = {"color": [0.2, 0.19, 0.175], "secondary_color": [0.1, 0.095, 0.088], "cell_scale": 2.5, "cracks": False, "roughness": 0.8}
MAX_STONES_LISTED = 500


def pair(description, low, high, default):
    return array({"type": "number", "minimum": low, "maximum": high}, description, 2, 2, default)


def plan_shore_stones(args, state):
    """The stones are realized into one object per shape variant, name_0 and so on: how many hold stones follows from the
    shore. The default granite is the material name_stone."""
    state.unknown(("object",))
    if "material" not in args:
        state.add("material", f"{args.get('name', 'ShoreStones')}_stone")


def stone_material(ctx, name, given):
    if given is not None:
        if given not in bpy.data.materials:
            raise bad_args(f"there is no material named {given}")
        return given
    material = f"{name}_stone"
    if material not in bpy.data.materials:
        stone_shape.run(ctx, "material_procedural", name=material, stone=STONE_MATERIAL)
    return material


@command(
    "shore_stones",
    "Stones along the water line: clustered, irregularly spaced, partly sunk, shaped from fracture, chip and abrade, angular to round by how far water moved them.",
    {
        "target": ref(string("Ground object the stones lie on, in world space (modifiers included)."), "object", EXISTS),
        "name": ref(string("Name prefix of the realized stone meshes (one per shape variant).", default="ShoreStones", max_length=BASE_NAME_LENGTH), "object", CREATES),
        "shore_width": length("Stones lie up to this many metres above the water line.", 2.0),
        "shore_depth": number("Stones also lie down to this many metres under the water line, in the shallows.", 0.0, MAX_RELIEF, 0.3),
        "cluster_density": length("Groups of stones per square metre of the shore band.", 0.03, MAX_STONE_GROUP_DENSITY),
        "per_cluster": length("Mean number of stones in a group (Poisson, at least one stone each).", 8.0, MAX_STONES_PER_GROUP),
        "cluster_radius": length("Spread of a group: standard deviation in metres of the stones' offsets from its centre.", 0.5),
        "size_range": pair("Smallest and largest longest side of a stone in metres.", LEAST_STONE_SIZE, MAX_STONE_SIZE, [0.12, 0.9]),
        "size_distribution": string("lognormal (grain sizes of gravel, Krumbein 1936: the range spans four standard deviations of the log) or power (many small, few large).", list(DISTRIBUTIONS_HERE), "lognormal"),
        "size_exponent": number("power: the exponent of the size distribution.", -POWER_EXPONENT, 0.0, -2.0),
        "sorting": number("How alike the stones of a group are in size: the share of the variance of log size that is between groups (0 mixes sizes freely, 1 makes a group uniform).", 0.0, FRACTION, 0.5),
        "burial": pair("Share of a stone's height sunk in the ground, drawn between these.", 0.0, FRACTION, [0.15, 0.5]),
        "tilt": number("Largest lean of a stone from the lie of the ground, in degrees.", 0.0, QUARTER_TURN, 12.0),
        "settle": number("How far a stone follows the slope: 0 stands upright, 1 lies on the ground's normal.", 0.0, FRACTION, 0.7),
        "worked_distance": length("Height above the water line over which waves still rework stones; the share of worked stones falls as exp(-height / this).", 0.8),
        "classes": integer("Shape classes from angular (a fresh fragment) to round (long worked); one class is of middling wear.", 1, MAX_STONE_CLASSES, 4),
        "variants": integer("Meshes built for each class; stones of a class share them.", 1, MAX_STONE_VARIANTS, 2),
        "material": ref(string("Existing material for the stones. Default: a granite built with material_procedural."), "material", EXISTS),
        "shore_wet": number("Darken and gloss the stones up to this many metres above the water line, as the shore is (0 leaves them dry).", 0.0, MAX_RELIEF, 0.5),
        "max_count": integer("Most stones to place.", 1, MAX_INSTANCES, 400),
        "seed": integer("Random seed; the same seed, ground and water give the same stones.", 0, MAX_SEED, 0),
    },
    ["target"],
    slow=True,
    plan=plan_shore_stones,
    family="liquids",
    intents=("stones along the shore of a lake or river", "natural clustered boulders and pebbles at the water line", "angular and rounded stones by how far water moved them"),
    nearest=(("scatter", "for copies of meshes you made, with Poisson spacing"), ("liquid_body", "to make the water first")),
)
def shore_stones(ctx, args):
    target = get_mesh_object(args["target"])
    low, high = args["size_range"]
    if low > high:
        raise bad_args("size_range must be [smallest, largest]")
    if args["size_distribution"] == "power" and high / low > 32.0:
        raise bad_args("with power, the largest stone may be at most 32 times the smallest")
    name = args["name"]
    classes, variants = args["classes"], args["variants"]
    if classes * variants > 32:
        raise bad_args("classes times variants is at most 32 meshes")
    names = [f"{name}_{index}" for index in range(classes * variants)]
    for item in names + [f"{name}_variant_{index}" for index in range(classes * variants)]:
        require_free_name(item)
    depsgraph = ctx.depsgraph()
    surface = read_surface(target, depsgraph)
    corners = liquid_masks.corner_depth(target, surface, depsgraph, args["shore_width"])
    if corners is None:
        raise bad_args("shore_stones needs water from liquid_body or liquid_fill in the scene")
    water = liquid_world.Water(liquid_world.liquid_objects(ctx.scene))
    ground = liquid_grid.Ground([target], depsgraph)
    rng = numpy.random.default_rng([args["seed"], 0x570F])
    layout = stone_plan.plan(surface, ground, water, corners, args, classes, rng)
    material = stone_material(ctx, name, args.get("material"))
    shapes, heights, rounds = [], [], []
    try:
        for index in range(classes * variants):
            transport = (index // variants) / max(classes - 1, 1) if classes > 1 else 0.5
            stone, height = stone_shape.build_stone(ctx, f"{name}_variant_{index}", transport, args["seed"] * 1000 + index, material)
            points, _ = stone_shape.mesh_arrays(stone)
            shapes.append(stone)
            heights.append(height)
            rounds.append(stone_shape.roundness(points))
        heights = numpy.array(heights)
        picks = layout["class"] * variants + rng.integers(0, variants, len(layout["class"]))
        placed = stone_plan.matrices(layout, heights, picks)
        objects = []
        for index, stone in enumerate(shapes):
            chosen = placed[picks == index]
            if len(chosen):
                objects.append(realized_copy(ctx, names[index], stone.data, [numpy_matrix(row) for row in chosen]))
    finally:
        for stone in shapes:
            mesh = stone.data
            bpy.data.objects.remove(stone)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    ctx.view_layer.update()
    result = report(layout, picks, variants, rounds, objects, args)
    if args["shore_wet"] > 0.0:
        result["wet"] = liquid_world.wet_shores(ctx, args["shore_wet"], [item.name for item in objects])
    return result


def numpy_matrix(rows):
    from mathutils import Matrix

    return Matrix(rows.tolist())


def report(layout, picks, variants, rounds, objects, args):
    sizes = layout["sizes"]
    count = len(sizes)
    classes = layout["class"]
    mean_round = [round(float(numpy.mean(rounds[index * variants:(index + 1) * variants])), 4) for index in range(args["classes"])]
    listed = min(count, MAX_STONES_LISTED)
    return {
        "name": args["name"],
        "objects": [item.name for item in objects],
        "count": count,
        "clusters": layout["clusters"],
        "band_area": round(layout["band_area"], 4),
        "nearest_neighbour_index": None if layout["index"] is None else round(layout["index"], 4),
        "size": {
            "distribution": args["size_distribution"],
            "median": round(float(numpy.median(sizes)), 4),
            "log_mean": round(float(numpy.mean(numpy.log(sizes))), 4),
            "log_deviation": round(float(numpy.std(numpy.log(sizes))), 4),
            "range": [round(float(sizes.min()), 4), round(float(sizes.max()), 4)],
        },
        "burial": [round(float(layout["burial"].min()), 4), round(float(layout["burial"].max()), 4)],
        "roundness": rounds,
        "class_roundness": mean_round,
        "class_counts": [int((classes == index).sum()) for index in range(args["classes"])],
        "stones": [
            {"position": [round(float(value), 4) for value in layout["points"][row]], "size": round(float(sizes[row]), 4), "class": int(classes[row]),
             "burial": round(float(layout["burial"][row]), 4), "height_above_water": round(float(layout["dry"][row]), 4), "group": int(layout["group"][row])}
            for row in range(listed)
        ],
        "meshes": [mesh_counts(item.data) for item in objects],
    }
