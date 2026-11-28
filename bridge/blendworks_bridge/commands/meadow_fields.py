"""Command meadow_fields."""
from ..cover_ground import shade_materials
from ..cover_structure import PATH_MODES
from ..errors import bad_args
from ..limits import LEAST_PATH_POINTS, MAX_SEED, MOST_PATH_POINTS
from ..meadow_fields import Settings, compute
from ..meadow_inputs import scene_objects
from ..registry import command
from ..schema import EXISTS, boolean, integer, names, points3, ref, string
from ..util import get_mesh_object


@command(
    "meadow_fields",
    "Compute a meadow's structure fields on ground meshes as point attributes: moisture, soil depth, disturbance with worn paths, shade and grazing.",
    {
        "targets": ref(names("Ground meshes, in world space; one terrain grid spans them all, so tiles get matching fields."), "object", EXISTS),
        "seed": integer("Random seed of the noise, the trodden patches and the path gates.", 0, MAX_SEED, 0),
        "shade": ref(names("Objects whose shadow along the sun shades the ground: tree crowns, shrubs, rocks."), "object", EXISTS),
        "obstacles": ref(names("Rocks and stones: water runs off them, so the ground at their foot is damper."), "object", EXISTS),
        "paths": string("auto: worn paths between the meadow's gates and its water; none: no paths.", list(PATH_MODES), "auto"),
        "path_points": points3("Join these points [x, y, z] in metres with the paths instead of the gates and the water.", LEAST_PATH_POINTS, MOST_PATH_POINTS),
        "materials": boolean("Give the targets' materials the meadow ground, which reads the fields.", True),
    },
    ["targets"],
    slow=True,
    family="ground_cover",
    intents=("moisture, soil and shade maps over a terrain for a meadow", "worn footpaths across a meadow to the water", "make the ground vary like a real meadow"),
    nearest=(("ground_cover", "to grow the cover itself; it computes the fields when its populations need them"), ("erode", "for erosion and deposition attributes")),
)
def meadow_fields(ctx, args):
    targets = [get_mesh_object(name) for name in dict.fromkeys(args["targets"])]
    if not all(len(obj.data.vertices) for obj in targets):
        raise bad_args("every target needs vertices")
    settings = Settings(args["seed"], scene_objects(args.get("shade", [])), scene_objects(args.get("obstacles", [])), args["paths"], args.get("path_points"))
    _, lines, report = compute(targets, ctx.scene, ctx.depsgraph(), settings)
    if args["materials"]:
        changed, skipped = shade_materials(targets)
        report["materials"] = changed
        if skipped:
            report["materials_skipped"] = skipped
    ctx.view_layer.update()
    return report
