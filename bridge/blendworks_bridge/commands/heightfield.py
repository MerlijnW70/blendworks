import math

import bpy
import numpy

from ..limits import MAX_COORDINATE, MAX_MESH_VERTICES
from ..mesh_attributes import write_attributes
from ..noise_stack import STACK_FIELDS, finest_wavelength, stack_bounds
from ..registry import command
from ..schema import array, boolean, integer, length, number, string
from ..terrain import TileMesh, grid_points, surface_heights
from ..util import check_vertex_cap, link_object, mesh_counts, require_free_name, rounded
from .noise_displace import ATTRIBUTE_FIELD

MAX_TILE_INDEX = 1_000
MAX_RESOLUTION = math.isqrt(MAX_MESH_VERTICES)


def positive_pair(description):
    item = {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_COORDINATE}
    return array(item, description, 2, 2, [100.0, 100.0])


@command(
    "heightfield",
    "Build a terrain tile from the noise stack at world metres, so neighbouring tiles share edge heights; optional closed skirt, UVs that continue across tiles, slope, height and curvature attributes.",
    {
        "name": string("New mesh object; must be unused."),
        "size": positive_pair("Tile size [x, y] in metres."),
        "resolution": integer("Vertices per side of the tile, at least 2; capped by the mesh vertex limit.", 2, MAX_RESOLUTION, 65),
        "tile": array({"type": "integer", "minimum": -MAX_TILE_INDEX, "maximum": MAX_TILE_INDEX}, "Tile index [i, j]: the tile covers world x from i*size_x and y from j*size_y, and the object sits there.", 2, 2, [0, 0]),
        "height": number("Height scale in metres: the noise (-1..1) times this is added to base_height, so no surface point is more than height from it.", 0.0, 10_000.0),
        "base_height": number("Mean surface level in metres; the surface stays within height of it."),
        "skirt": boolean("Close the tile into a solid: walls down to a flat underside, so it passes the manifold rule.", False),
        "skirt_depth": length("skirt: metres from the lowest height the noise can reach (base_height + height times its lowest value) down to the underside, the same for every tile.", 1.0, 10_000.0),
        "attributes": ATTRIBUTE_FIELD,
        **STACK_FIELDS,
    },
    ["name", "height"],
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
    if "attributes" in args:
        result["attributes"] = write_attributes(obj, args["attributes"], (resolution - 1) ** 2, resolution * resolution)
    return result
