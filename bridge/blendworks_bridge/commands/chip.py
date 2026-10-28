import numpy

from .. import kit_limits
from ..errors import failed
from ..fracturing import chip_once
from ..fragments import require_convex, slot_layout, solid_from_object, write_solid
from ..registry import command
from ..schema import integer, length, string
from ..util import get_mesh_object, mesh_counts, rounded


@command(
    "chip",
    "Knock chips off the edges and corners of a closed convex solid with exact random planar cuts; each removes volume only within depth of the edge it hit, and the result stays closed.",
    {
        "name": string("Closed convex mesh object to chip; it keeps its transform."),
        "count": integer("Number of chips to cut.", 1, kit_limits.MAX_CHIPS, 3),
        "depth": length("Largest distance in metres from the hit edge or corner to any removed point.", 0.02),
        "seed": integer("Random seed; the same seed gives the same chips.", 0, 2**31 - 1, 0),
        "fresh_material": string("Existing material for the fresh faces' own slot; default creates FreshBreak."),
    },
    ["name"],
    slow=True,
    family="shapes",
    intents=("chip the corners and edges off a stone", "knock random chunks off a block", "break edges of a rock with planar cuts"),
    nearest=(("fracture", "to break the whole solid into pieces"), ("abrade", "to round edges smoothly instead of cutting them")),
)
def chip(ctx, args):
    obj = get_mesh_object(args["name"])
    ctx.view_layer.update()
    solid = solid_from_object(obj, ctx.depsgraph())
    require_convex(solid, obj.name)
    before = solid.volume()
    slots, fresh = slot_layout(obj.data, args.get("fresh_material"))
    rng = numpy.random.default_rng(args["seed"])
    removed = []
    for _ in range(args["count"]):
        result = chip_once(solid, rng, args["depth"], fresh)
        if result is None:
            continue
        solid, cut = result
        removed.append(cut.volume())
    if not removed:
        raise failed(f"no chip of depth {args['depth']} m fits on {obj.name}; use a larger depth or a solid with sharper edges")
    inverse = numpy.linalg.inv(numpy.array(obj.matrix_world, dtype=numpy.float64))
    write_solid(obj.data, solid, numpy.zeros(3), slots, inverse)
    return {
        "name": obj.name,
        "chips": len(removed),
        "requested": args["count"],
        "removed_volume": rounded(sum(removed), 9),
        "volume_before": rounded(before, 9),
        "volume_after": rounded(solid.volume(), 9),
        "fresh_slot": fresh,
        "mesh": mesh_counts(obj.data),
    }
