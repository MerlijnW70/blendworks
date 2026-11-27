import bpy
import numpy

from .. import kit_limits
from ..errors import bad_args, failed
from ..fracturing import binary_pieces, seed_points, voronoi_cells
from ..fragments import UV_NAME, plan_fresh_material, require_convex, slot_layout, solid_from_object, solid_stats, write_solid
from ..registry import command
from ..limits import MAX_SEED, PAIR
from ..schema import EXISTS, boolean, integer, length, ref, string
from ..util import get_mesh_object, rounded

MODES = ("binary", "voronoi")


def piece_name(base, number):
    return f"{base}_piece_{number:03d}"


def make_piece(source, name, solid, slots):
    origin = solid.centroid()
    mesh = bpy.data.meshes.new(name)
    write_solid(mesh, solid, origin, slots)
    obj = bpy.data.objects.new(name, mesh)
    for collection in source.users_collection or [bpy.context.scene.collection]:
        collection.objects.link(obj)
    obj.location = tuple(origin)
    return obj


def plan_fracture(args, state):
    """The pieces are name_piece_000 and on, as many as asked for (fewer only when min_size leaves no room); the
    source goes unless keep_original."""
    plan_fresh_material(args, state)
    for number in range(args["pieces"]):
        state.add("object", piece_name(args["name"], number))
    if not args["keep_original"]:
        state.remove("object", args["name"])


@command(
    "fracture",
    "Break a closed convex solid into closed convex pieces by exact plane cuts (binary splits or Voronoi cells); cut faces get box-mapped UVs in metres and a fresh-break material slot.",
    {
        "name": ref(string("Closed convex mesh object to break; its transform is baked into the pieces (metres)."), "object", EXISTS),
        "pieces": integer("Number of pieces (fewer if min_size leaves no room).", PAIR, kit_limits.MAX_FRACTURE_PIECES, 8),
        "mode": string("binary splits the largest piece by a random plane near its centroid again and again (blocky fragments, about 6 faces and 8 vertices each); voronoi cuts cells by bisector planes between random seed points.", list(MODES), "binary"),
        "seed": integer("Random seed; the same seed gives the same pieces.", 0, MAX_SEED, 0),
        "min_size": length("Smallest allowed thickness of a piece in metres: the distance from any face plane of the piece to its farthest point; 0.0001 allows slivers.", 0.01),
        "fresh_material": ref(string("Existing material for the fresh faces' own slot; default creates FreshBreak."), "material", EXISTS),
        "keep_original": boolean("Keep the source object beside its pieces instead of deleting it.", False),
    },
    ["name"],
    slow=True,
    plan=plan_fracture,
    family="shapes",
    intents=("break a boulder into blocky fragments", "fracture a block into voronoi shards", "shatter a rock into pieces that add up to the original"),
    nearest=(("boolean", "to cut with cutters you place yourself"), ("chip", "to knock small corners off one stone")),
)
def fracture(ctx, args):
    source = get_mesh_object(args["name"])
    ctx.view_layer.update()
    solid = solid_from_object(source, ctx.depsgraph())
    require_convex(solid, source.name)
    slots, fresh = slot_layout(source.data, args.get("fresh_material"))
    rng = numpy.random.default_rng(args["seed"])
    min_size = args["min_size"]
    if args["mode"] == "binary":
        cells = binary_pieces(solid, args["pieces"], rng, min_size, fresh)
    else:
        seeds = seed_points(solid, args["pieces"], rng, min_size)
        if len(seeds) < 2:
            raise failed(f"{source.name} has no room for two Voronoi seeds {min_size} m apart; lower min_size")
        cells = voronoi_cells(solid, seeds, fresh)
    if len(cells) < 2:
        raise failed(f"{source.name} could not be cut into pieces of at least {min_size} m; lower min_size")
    names = [piece_name(source.name, number) for number in range(len(cells))]
    taken = [name for name in names if name in bpy.data.objects]
    if taken:
        raise bad_args(f"an object named {taken[0]} already exists")
    objects = [make_piece(source, name, cell, slots) for name, cell in zip(names, cells)]
    total = sum(cell.volume() for cell in cells)
    original = solid.volume()
    counts = numpy.array([solid_stats(cell) for cell in cells], dtype=float)
    if not args["keep_original"]:
        mesh = source.data
        bpy.data.objects.remove(source)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return {
        "name": args["name"],
        "mode": args["mode"],
        "pieces": names,
        "volumes": [rounded(cell.volume(), 9) for cell in cells],
        "centres": [[rounded(value, 6) for value in cell.centroid()] for cell in cells],
        "count": len(names),
        "original_volume": rounded(original, 9),
        "pieces_volume": rounded(total, 9),
        "volume_error": rounded(abs(total - original) / original, 9),
        "mean_faces": rounded(counts[:, 0].mean(), 4),
        "mean_vertices": rounded(counts[:, 1].mean(), 4),
        "fresh_slot": fresh,
        "fresh_material": slots[fresh].name,
        "uv_map": UV_NAME,
    }
