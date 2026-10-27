import numpy
from mathutils import Matrix

from ..copies import linked_copies, realized_copy
from ..errors import bad_args
from ..kit_limits import MAX_INSTANCES
from ..noise_stack import STACK_FIELDS
from ..registry import command
from ..scatter_frames import ALIGNMENTS
from ..scatter_masks import MASKS, chosen_masks
from ..scatter_plan import plan_scatter
from ..scatter_sizes import DISTRIBUTIONS
from ..scatter_surface import read_surface
from ..schema import array, boolean, described, integer, length, number, obj, string
from ..util import get_mesh_object, link_object, mesh_counts, require_free_name
from .placement import place_copies

SOURCE = described(
    obj(
        {
            "name": string("Mesh object whose mesh is copied; its own transform is not used and its origin is the point set on the surface."),
            "weight": number("Relative share of the instances.", exclusive_minimum=0, maximum=1_000_000.0, default=1.0),
        },
        ["name"],
    ),
    "One mesh to scatter and its weight.",
)

NOISE = described(
    obj(
        {
            **STACK_FIELDS,
            "threshold": number("Noise value, scaled to 0..1, at which the density is half; higher keeps fewer instances.", 0.0, 1.0, 0.5),
            "softness": number("Width of the change from no instances to full density, in scaled noise units.", exclusive_minimum=0, maximum=1.0, default=0.2),
        },
        ["scale"],
    ),
    "A noise stack in metres, the same fields as noise_displace, scaled to 0..1 and turned into a density.",
)


def range_pair(description, low, high, default=None):
    return array({"type": "number", "minimum": low, "maximum": high}, description, 2, 2, default)


def sources_from(args):
    if ("source" in args) == ("sources" in args):
        raise bad_args("give the meshes as exactly one of source or sources")
    entries = [{"name": args["source"], "weight": 1.0}] if "source" in args else args["sources"]
    names = [entry["name"] for entry in entries]
    if len(set(names)) != len(names):
        raise bad_args("a source is listed twice")
    return [(get_mesh_object(entry["name"]), entry["weight"]) for entry in entries]


def source_height(mesh):
    if not len(mesh.vertices):
        raise bad_args(f"{mesh.name} has no vertices")
    coordinates = numpy.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coordinates)
    heights = coordinates[2::3]
    return float(heights.max() - heights.min())


def matrix_list(rows):
    return [Matrix(row.tolist()) for row in rows]


def place_sources(ctx, args, sources, plan):
    if len(sources) == 1:
        return place_copies(ctx, args, sources[0][0].data, matrix_list(plan.matrices))
    pieces = [(source.name, source.data, matrix_list(plan.matrices[plan.source_ids == index])) for index, (source, _) in enumerate(sources)]
    pieces = [piece for piece in pieces if piece[2]]
    if args["realize"]:
        names = [f"{args['name']}_{name}" for name, _, _ in pieces]
        for name in names:
            require_free_name(name)
        merged = [realized_copy(ctx, name, mesh, matrices) for name, (_, mesh, matrices) in zip(names, pieces)]
        ctx.view_layer.update()
        return {"name": merged[0].name, "objects": [item.name for item in merged], "realized": True, "mesh": [mesh_counts(item.data) for item in merged]}
    require_free_name(args["name"] if args["group"] else None)
    parent = link_object(ctx, args["name"], None) if args["group"] else None
    names = []
    for name, mesh, matrices in pieces:
        _, copies = linked_copies(ctx, f"{args['name']}_{name}", mesh, matrices, False)
        for item in copies:
            if parent is not None:
                item.parent = parent
        names.extend(item.name for item in copies)
    ctx.view_layer.update()
    return {"name": parent.name if parent is not None else names[0], "objects": names[:3] if len(names) > 3 else names, "realized": False}


@command(
    "scatter",
    "Scatter copies of one or more meshes over a surface with Poisson disk spacing in metres, density masks, a size distribution, alignment to the surface and an embed; reports the smallest distance.",
    {
        "target": string("Mesh object to scatter over, in world space (modifiers included)."),
        "source": string("Mesh object whose mesh is copied; its origin is the point set on the surface, so model it with its base at the origin."),
        "sources": array(SOURCE, "Several meshes with weights; each instance picks one with probability proportional to its weight.", 1, 64),
        "min_distance": length("Smallest distance in metres between two instances, measured in 3D, so spacing holds on steep slopes. With power it is the distance between the smallest instances; larger ones keep the sum of their radii, min_distance times (a + b) / (2 smallest scale) for scales a and b."),
        "density": length("A cap in candidate points per square metre: no more than density times the surface area instances are placed. Leave out to fill the surface."),
        "density_mask": array(string("A mask.", list(MASKS)), "Masks that multiply the density, each in 0..1: slope (needs slope_range), height (height_range), vertex_group, noise, attribute (attribute and attribute_range).", 1, len(MASKS)),
        "slope_range": range_pair("slope mask: keep faces whose normal is between these angles from vertical, in degrees.", 0.0, 180.0),
        "height_range": range_pair("height mask: keep points between these world heights in metres.", -1_000_000.0, 1_000_000.0),
        "vertex_group": string("vertex_group mask: the weight of this vertex group is the density."),
        "noise": NOISE,
        "attribute": string("attribute mask: a float attribute of the target, such as the slope or height that heightfield writes (point, face or corner domain)."),
        "attribute_range": range_pair("attribute mask: density rises from 0 at the first value to 1 at the second; equal values make a hard threshold.", -1_000_000.0, 1_000_000.0),
        "scale_range": array({"type": "number", "exclusiveMinimum": 0, "maximum": 1000.0}, "Smallest and largest scale of an instance.", 2, 2, [1.0, 1.0]),
        "scale_distribution": string("How scales are drawn: uniform, lognormal (the range spans four standard deviations of the log) or power (count proportional to scale to the exponent, many small and few large).", list(DISTRIBUTIONS), "uniform"),
        "scale_exponent": number("power: the exponent of the size distribution; -2 is the size structure of tree communities (Enquist and Niklas 2001).", -8.0, 0.0, -2.0),
        "align": string("normal turns the instance Z axis to the surface normal; up keeps it vertical; blend mixes the two by align_factor.", list(ALIGNMENTS), "normal"),
        "align_factor": number("blend: 0 is upright, 1 follows the surface normal.", 0.0, 1.0, 0.5),
        "random_yaw": boolean("Turn every instance by a random angle about its own Z axis.", True),
        "tilt": number("Lean every instance away from its axis by a random angle up to this many degrees.", 0.0, 90.0, 0.0),
        "embed": number("Sink every instance along its axis by this fraction of its scaled height (the source's size in Z), so it does not float on a slope.", 0.0, 1.0, 0.0),
        "seed": integer("Random seed; the same seed, surface and settings give the same instances whatever the order of the faces.", 0, 2**31 - 1, 0),
        "max_count": integer("Most instances to place.", 1, MAX_INSTANCES, MAX_INSTANCES),
        "name": string("Name of the group (linked copies) or of the realised mesh; copies are named name_000, name_001 and so on.", default="Scatter"),
        "realize": boolean("Merge the copies into one real mesh (for export) instead of linked objects.", False),
        "group": boolean("Parent linked copies to an empty named name so they move together.", True),
    },
    ["target", "min_distance"],
    slow=True,
    family="placement",
    intents=("scatter rocks or plants over terrain with natural spacing", "poisson disk points on a surface with density masks", "random sizes with a power law, aligned to the slope"),
    nearest=(("instances", "for copies at points you give"), ("heightfield", "to make the terrain first")),
)
def scatter(ctx, args):
    target = get_mesh_object(args["target"])
    masks = chosen_masks(args)
    sources = sources_from(args)
    if any(source is target for source, _ in sources):
        raise bad_args("the target cannot also be a source")
    surface = read_surface(target, ctx.depsgraph(), args.get("attribute") if "attribute" in masks else None, args.get("vertex_group") if "vertex_group" in masks else None)
    weights = numpy.array([weight for _, weight in sources])
    plan = plan_scatter(surface, args, masks, weights, numpy.array([source_height(source.data) for source, _ in sources]))
    if plan.report["count"] == 0:
        raise bad_args("no instance fits: the masks removed every candidate or the surface is smaller than min_distance")
    result = place_sources(ctx, args, sources, plan)
    result.update(plan.report)
    return result
