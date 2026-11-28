"""UV commands: uv_smart_project, uv_unwrap and uv_info."""

import math

import bpy
import numpy

from .. import limits
from ..errors import bad_args, not_found
from ..operators import edit_mode
from ..registry import command
from ..limits import FRACTION, HALF_TURN, QUARTER_TURN, SMALLEST_SPLIT_ANGLE, UV_MARGIN
from ..schema import boolean, integer, number, ref, string
from ..texel import density, pack, scale_to_density
from ..uv_coverage import merge_islands
from ..uv_project import project_by_angle
from ..util import EditMesh, get_mesh_object, rounded

GRID = 256
SAMPLE_SHIFT = 0.000123


def uv_mesh_object(name):
    obj = get_mesh_object(name)
    if len(obj.data.polygons) == 0:
        raise bad_args(f"{obj.name} has no faces to unwrap")
    if obj.data.users > 1:
        raise bad_args(f"{obj.name} shares its mesh with other objects; duplicate it without linking first")
    return obj


def run_in_edit_mode(ctx, obj, operator):
    if len(obj.data.uv_layers) == 0:
        obj.data.uv_layers.new(name="UVMap")
    with edit_mode(ctx.view_layer, obj):
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action="SELECT")
        operator()
    obj.data.update()


TEXEL_PROPERTIES = {
    "texel_density": number(
        "Scale the islands to this many texture pixels per metre, then pack them without rescaling; they may spill out of the UV square.",
        maximum=limits.MAX_TEXEL_DENSITY,
        exclusive_minimum=0.0,
    ),
    "texture_size": integer("Texture size in pixels that texel densities refer to.", 1, limits.MAX_TEXTURE_SIZE, 1024),
}


def apply_texel_density(ctx, obj, args, margin):
    if "texel_density" not in args:
        return
    scale_to_density(obj, obj.data.uv_layers.active, args["texel_density"], args["texture_size"])
    pack(ctx.view_layer, [obj], margin, False, False)


@command(
    "uv_smart_project",
    "UV-unwrap a mesh automatically by splitting it into islands at sharp angles.",
    {
        "name": ref(string("Mesh object."), "object"),
        "angle_limit": number("Split islands where faces meet at more than this many degrees.", SMALLEST_SPLIT_ANGLE, QUARTER_TURN, 66.0),
        "island_margin": number("Space between islands, as a share of the UV square.", 0.0, UV_MARGIN, 0.02),
        "min_island_area": number(
            "Merge islands smaller than this share of the surface area into a neighbour where the seams allow, then pack; stops slivers on notched parts. 0 keeps every island.",
            0.0,
            FRACTION,
            0.0,
        ),
        **TEXEL_PROPERTIES,
    },
    ["name"],
    family="uv",
    intents=("automatic UV unwrap without seams", "unwrap by angle, merge small islands"),
    nearest=(("uv_unwrap", "when seams are marked"),),
)
def uv_smart_project(ctx, args):
    obj = uv_mesh_object(args["name"])
    merging = args["min_island_area"] > 0
    if len(obj.data.uv_layers) == 0:
        obj.data.uv_layers.new(name="UVMap")
    project_by_angle(obj, math.radians(args["angle_limit"]))
    run_in_edit_mode(
        ctx,
        obj,
        lambda: bpy.ops.uv.pack_islands(
            udim_source="CLOSEST_UDIM",
            rotate=True,
            rotate_method="AXIS_ALIGNED_Y",
            scale=True,
            margin_method="FRACTION",
            margin=0.0 if merging else args["island_margin"],
            shape_method="AABB",
        ),
    )
    islands = None
    if merging:
        islands = merge_islands(obj, args["min_island_area"])
        pack(ctx.view_layer, [obj], args["island_margin"], False, True, "ANY", "CONVEX")
    apply_texel_density(ctx, obj, args, args["island_margin"])
    report = uv_report(obj, texture_size=args["texture_size"])
    if islands is not None:
        report["islands"] = islands
    return report


@command(
    "uv_unwrap",
    "UV-unwrap a mesh along its seams; seam_angle first marks edges sharper than it as seams.",
    {
        "name": ref(string("Mesh object."), "object"),
        "method": string("Unwrap method.", ["angle_based", "conformal", "minimum_stretch"], "angle_based"),
        "margin": number("Space between islands, as a share of the UV square.", 0.0, UV_MARGIN, 0.02),
        "seam_angle": number("Mark edges whose faces meet at more than this many degrees as seams first.", 0.0, HALF_TURN),
        "clear_seams": boolean("Clear existing seams before marking new ones.", False),
        **TEXEL_PROPERTIES,
    },
    ["name"],
    family="uv",
    intents=("unwrap along marked seams", "mark seams by angle and unwrap"),
    nearest=(("uv_smart_project", "for fully automatic islands"),),
)
def uv_unwrap(ctx, args):
    obj = uv_mesh_object(args["name"])
    if "seam_angle" in args or args["clear_seams"]:
        threshold = math.radians(args.get("seam_angle", 360.0))
        with EditMesh(obj) as bm:
            for edge in bm.edges:
                sharp = len(edge.link_faces) == 2 and edge.calc_face_angle(0.0) > threshold
                edge.seam = sharp or (edge.seam and not args["clear_seams"])
    run_in_edit_mode(
        ctx,
        obj,
        lambda: bpy.ops.uv.unwrap(method=args["method"].upper(), margin_method="FRACTION", margin=args["margin"], correct_aspect=True),
    )
    apply_texel_density(ctx, obj, args, args["margin"])
    report = uv_report(obj, texture_size=args["texture_size"])
    report["seams"] = sum(1 for edge in obj.data.edges if edge.use_seam)
    return report


@command(
    "uv_info",
    "Measure a mesh's UVs: coverage of the 0-1 square, overlap, and texel density in pixels per metre.",
    {
        "name": ref(string("Mesh object."), "object"),
        "layer": string("UV layer. Default: the active one."),
        "texture_size": TEXEL_PROPERTIES["texture_size"],
    },
    ["name"],
    mutates=False,
    family="uv",
    intents=("measure UV coverage, overlap and texel density",),
    nearest=(("uv_pack", "to improve the layout"),),
)
def uv_info(ctx, args):
    obj = get_mesh_object(args["name"])
    return uv_report(obj, args.get("layer"), args["texture_size"])


def uv_report(obj, layer_name=None, texture_size=1024):
    mesh = obj.data
    layers = [layer.name for layer in mesh.uv_layers]
    if layer_name is not None and layer_name not in layers:
        raise not_found(f"{obj.name} has no UV layer named {layer_name}")
    layer = mesh.uv_layers.get(layer_name) if layer_name else mesh.uv_layers.active
    if layer is None:
        return {"name": obj.name, "has_uv": False, "layers": layers}
    covered, overlapped, outside, area = rasterize(mesh, layer)
    return {
        "name": obj.name,
        "has_uv": True,
        "layer": layer.name,
        "layers": layers,
        "coverage": rounded(covered / (GRID * GRID), 4),
        "overlap": rounded(overlapped / covered, 4) if covered else 0.0,
        "outside": outside,
        "uv_area": rounded(area, 4),
        "texel_density": density(obj, layer, texture_size),
    }


CELL_CHUNK = 1 << 22


def loop_uvs(mesh, layer):
    flat = numpy.empty(len(layer.data) * 2, dtype=numpy.float32)
    layer.data.foreach_get("uv", flat)
    starts = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    totals = numpy.empty(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    return flat.astype(numpy.float64).reshape(-1, 2), starts, totals


def fan_triangles(starts, totals):
    fans = numpy.maximum(totals - 2, 0)
    polygon = numpy.repeat(numpy.arange(len(starts)), fans)
    step = numpy.arange(int(fans.sum())) - numpy.repeat(numpy.cumsum(fans) - fans, fans) + 1
    first = starts[polygon]
    return polygon, numpy.stack((first, first + step, first + step + 1), axis=1)


def rasterize(mesh, layer):
    uv, starts, totals = loop_uvs(mesh, layer)
    used = numpy.zeros(len(uv), dtype=bool)
    used[numpy.repeat(starts, totals) + numpy.arange(int(totals.sum())) - numpy.repeat(numpy.cumsum(totals) - totals, totals)] = True
    inside = (uv >= 0.0) & (uv <= 1.0)
    outside = bool((~(inside[:, 0] & inside[:, 1]))[used].any())
    polygon, corners = fan_triangles(starts, totals)
    a, b, c = uv[corners[:, 0]], uv[corners[:, 1]], uv[corners[:, 2]]
    halves = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])) / 2.0
    area = float(numpy.cumsum(numpy.concatenate(([0.0], numpy.abs(halves))))[-1])
    doubled = halves * 2.0
    solid = numpy.abs(doubled) >= 1e-14
    keys = cell_keys(polygon[solid], a[solid], b[solid], c[solid], doubled[solid])
    cells = numpy.unique(keys) % (GRID * GRID)
    counts = numpy.minimum(numpy.bincount(cells, minlength=GRID * GRID), 2)
    return int((counts > 0).sum()), int((counts > 1).sum()), outside, area


def cell_keys(polygon, a, b, c, doubled):
    points = numpy.stack((a, b, c), axis=1)
    low = numpy.maximum(0, numpy.floor(points.min(axis=1) * GRID)).astype(numpy.int64)
    high = numpy.minimum(GRID - 1, numpy.floor(points.max(axis=1) * GRID)).astype(numpy.int64)
    width = numpy.maximum(high[:, 0] - low[:, 0] + 1, 0)
    height = numpy.maximum(high[:, 1] - low[:, 1] + 1, 0)
    sizes = width * height
    found = []
    begin = 0
    while begin < len(sizes):
        end = begin + max(1, int(numpy.searchsorted(numpy.cumsum(sizes[begin:]), CELL_CHUNK)))
        found.append(chunk_keys(slice(begin, end), polygon, a, b, c, doubled, low, width, sizes))
        begin = end
    return numpy.concatenate(found) if found else numpy.empty(0, dtype=numpy.int64)


def chunk_keys(part, polygon, a, b, c, doubled, low, width, sizes):
    counts = sizes[part]
    owner = numpy.repeat(numpy.arange(part.start, part.start + len(counts)), counts)
    offset = numpy.arange(int(counts.sum())) - numpy.repeat(numpy.cumsum(counts) - counts, counts)
    x = low[owner, 0] + offset % width[owner]
    y = low[owner, 1] + offset // numpy.maximum(width[owner], 1)
    px = (x + 0.5) / GRID + SAMPLE_SHIFT
    py = (y + 0.5) / GRID + SAMPLE_SHIFT
    a, b, c, doubled = a[owner], b[owner], c[owner], doubled[owner]
    first = ((b[:, 0] - px) * (c[:, 1] - py) - (c[:, 0] - px) * (b[:, 1] - py)) / doubled
    second = ((c[:, 0] - px) * (a[:, 1] - py) - (a[:, 0] - px) * (c[:, 1] - py)) / doubled
    hit = (first >= 0) & (second >= 0) & (first + second <= 1)
    return polygon[owner[hit]] * (GRID * GRID) + (y * GRID + x)[hit]


def signed_area(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0


def triangle_cells(triangle):
    a, b, c = triangle
    doubled = signed_area(a, b, c) * 2.0
    if abs(doubled) < 1e-14:
        return []
    low_x = max(0, int(math.floor(min(a[0], b[0], c[0]) * GRID)))
    high_x = min(GRID - 1, int(math.floor(max(a[0], b[0], c[0]) * GRID)))
    low_y = max(0, int(math.floor(min(a[1], b[1], c[1]) * GRID)))
    high_y = min(GRID - 1, int(math.floor(max(a[1], b[1], c[1]) * GRID)))
    hits = []
    for y in range(low_y, high_y + 1):
        py = (y + 0.5) / GRID + SAMPLE_SHIFT
        for x in range(low_x, high_x + 1):
            px = (x + 0.5) / GRID + SAMPLE_SHIFT
            first = ((b[0] - px) * (c[1] - py) - (c[0] - px) * (b[1] - py)) / doubled
            second = ((c[0] - px) * (a[1] - py) - (a[0] - px) * (c[1] - py)) / doubled
            if first >= 0 and second >= 0 and first + second <= 1:
                hits.append(y * GRID + x)
    return hits
