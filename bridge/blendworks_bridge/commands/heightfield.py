"""The heightfield command: a terrain tile from the noise stack at world coordinates."""

import bpy
import numpy

from ..limits import MAX_COORDINATE, MAX_GRID_SIDE, MAX_RELIEF, MAX_TILE_INDEX as TILE_INDEX_LIMIT, PAIR
from .. import ground_form
from ..mesh_attributes import write_attributes
from ..noise_stack import STACK_FIELDS, finest_wavelength, stack_bounds
from ..registry import command
from ..schema import CREATES, array, boolean, integer, length, number, ref, string
from ..terrain import TileMesh, grid_points, surface_heights
from ..util import check_vertex_cap, link_object, mesh_counts, require_free_name, rounded
from .noise_displace import ATTRIBUTE_FIELD

MAX_TILE_INDEX = TILE_INDEX_LIMIT
MAX_RESOLUTION = MAX_GRID_SIDE


def positive_pair(description):
    item = {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_COORDINATE}
    return array(item, description, 2, 2, [100.0, 100.0])


def tile_inside_world(args):
    """The tile covers world x from tile[0] * size[0] to (tile[0] + 1) * size[0], and so for y; both ends must stay
    within the coordinate limit."""
    problems = []
    for axis, label in enumerate("xy"):
        ends = [args["tile"][axis] * args["size"][axis], (args["tile"][axis] + 1) * args["size"][axis]]
        far = max(ends, key=abs)
        if abs(far) > MAX_COORDINATE:
            problems.append({"argument": f"args.tile[{axis}]", "value": args["tile"][axis],
                             "limit": {"name": MAX_COORDINATE.key, "value": MAX_COORDINATE.plain()},
                             "message": f"args.tile[{axis}] times args.size[{axis}] puts the tile's {label} edge at {far:g} m, past "
                                        f"the coordinate limit {MAX_COORDINATE.plain():g} m ({MAX_COORDINATE.reason})",
                             "instead": "a larger size with a smaller tile index, or fewer tiles"})
    return problems


@command(
    "heightfield",
    "Build a terrain tile from the noise stack at world metres, so neighbouring tiles share edge heights; optional closed skirt, UVs that continue across tiles, slope, height and curvature attributes.",
    {
        "name": ref(string("New mesh object; must be unused."), "object", CREATES),
        "size": positive_pair("Tile size [x, y] in metres."),
        "resolution": integer("Vertices per side of the tile, at least 2; capped by the mesh vertex limit.", PAIR, MAX_RESOLUTION, 65),
        "tile": array({"type": "integer", "minimum": -MAX_TILE_INDEX, "maximum": MAX_TILE_INDEX}, "Tile index [i, j]: the tile covers world x from i*size_x and y from j*size_y, and the object sits there.", 2, 2, [0, 0]),
        "height": number("Height scale in metres: the noise (-1..1) times this is added to base_height, so no surface point is more than height from it.", 0.0, MAX_RELIEF),
        "base_height": number("Mean surface level in metres; the surface stays within height of it."),
        "skirt": boolean("Close the tile into a solid: walls down to a flat underside, so it passes the manifold rule.", False),
        "skirt_depth": length("skirt: metres from the lowest height the noise can reach (base_height + height times its lowest value) down to the underside, the same for every tile.", 1.0, MAX_RELIEF),
        "attributes": ATTRIBUTE_FIELD,
        "form": string("worn (the default): real ground damage on the noise surface, by process: slopes steeper than soil can stand fail and leave bare scars, rills cut along the flow where its stream power passes a threshold, and tussock hummocks rise on gentle grassland; it also stores each vertex's micro-relief (ground_relief) that render_final displaces near the camera; the forms fade out at the tile's edges so tiles still meet. none: the smooth noise surface alone.", ["worn", "none"], "worn"),
        **STACK_FIELDS,
    },
    ["name", "height"],
    rules=tile_inside_world,
    slow=True,
    family="shapes",
    intents=("terrain tile or heightfield from noise", "landscape ground with ridged mountains, in tiles that join without seams"),
    nearest=(("noise_displace", "to roughen an existing mesh"), ("add_primitive", "for a plain plane")),
)
def heightfield(ctx, args):
    require_free_name(args["name"])
    size, resolution, tile = args["size"], args["resolution"], args["tile"]
    skirt = args["skirt"]
    base_height = args.get("base_height", 0.0)
    floor = base_height + args["height"] * stack_bounds(args)[0] - args["skirt_depth"] if skirt else None
    check_vertex_cap(resolution * resolution + (4 * (resolution - 1) if skirt else 0))
    columns, rows = grid_points(size, resolution, tile)
    heights = surface_heights(columns, rows, args, args["height"], base_height)
    formed = None
    if args["form"] == "worn":
        heights, relief, _, formed = ground_form.worn(heights, resolution, size, columns, rows, args.get("seed", 0))
    origin = numpy.array([tile[0] * size[0], tile[1] * size[1]])
    shape = TileMesh(columns - origin[0], rows - origin[1], heights, resolution, size, tile, floor)
    mesh = bpy.data.meshes.new(args["name"])
    shape.build(mesh)
    obj = link_object(ctx, args["name"], mesh)
    obj.location = (float(origin[0]), float(origin[1]), 0.0)
    ctx.view_layer.update()
    result = {
        "name": obj.name,
        "mesh": mesh_counts(mesh),
        "tile": list(tile),
        "size": list(size),
        "max_displacement": rounded(float(numpy.abs(heights - base_height).max()), 9),
        "height_range": [rounded(float(heights.min()), 9), rounded(float(heights.max()), 9)],
    }
    spacing = max(size[0], size[1]) / (resolution - 1)
    result["spacing"] = rounded(spacing, 9)
    result["finest_wavelength"] = rounded(finest_wavelength(args), 9)
    if finest_wavelength(args) < 2.0 * spacing:
        result["warning"] = "the finest octave is shorter than two vertex spacings and shows as aliased noise; use fewer octaves or a higher resolution"
    if formed is not None:
        ground_form.store_relief(obj, relief)
        result["form"] = formed
    if "attributes" in args:
        result["attributes"] = write_attributes(obj, args["attributes"], (resolution - 1) ** 2, resolution * resolution)
    return result
