import math

import bpy

from .. import limits
from ..errors import bad_args, not_found
from ..operators import edit_mode
from ..registry import command
from ..schema import boolean, integer, number, string
from ..texel import density, pack, scale_to_density
from ..uv_coverage import merge_islands
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
        "name": string("Mesh object."),
        "angle_limit": number("Split islands where faces meet at more than this many degrees.", 1.0, 89.0, 66.0),
        "island_margin": number("Space between islands, as a share of the UV square.", 0.0, 1.0, 0.02),
        "min_island_area": number(
            "Merge islands smaller than this share of the surface area into a neighbour where the seams allow, then pack; stops slivers on notched parts. 0 keeps every island.",
            0.0,
            1.0,
            0.0,
        ),
        **TEXEL_PROPERTIES,
    },
    ["name"],
)
def uv_smart_project(ctx, args):
    obj = uv_mesh_object(args["name"])
    merging = args["min_island_area"] > 0
    run_in_edit_mode(
        ctx,
        obj,
        lambda: bpy.ops.uv.smart_project(
            angle_limit=math.radians(args["angle_limit"]),
            margin_method="FRACTION",
            island_margin=0.0 if merging else args["island_margin"],
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=False,
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
        "name": string("Mesh object."),
        "method": string("Unwrap method.", ["angle_based", "conformal", "minimum_stretch"], "angle_based"),
        "margin": number("Space between islands, as a share of the UV square.", 0.0, 1.0, 0.02),
        "seam_angle": number("Mark edges whose faces meet at more than this many degrees as seams first.", 0.0, 180.0),
        "clear_seams": boolean("Clear existing seams before marking new ones.", False),
        **TEXEL_PROPERTIES,
    },
    ["name"],
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
        "name": string("Mesh object."),
        "layer": string("UV layer. Default: the active one."),
        "texture_size": TEXEL_PROPERTIES["texture_size"],
    },
    ["name"],
    mutates=False,
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
    uvs = [tuple(item.uv) for item in layer.data]
    covered, overlapped, outside, area = rasterize(mesh, uvs)
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


def rasterize(mesh, uvs):
    counts = bytearray(GRID * GRID)
    outside = False
    area = 0.0
    for polygon in mesh.polygons:
        corners = [uvs[index] for index in polygon.loop_indices]
        if any(not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0) for u, v in corners):
            outside = True
        cells = set()
        for second in range(1, len(corners) - 1):
            triangle = (corners[0], corners[second], corners[second + 1])
            area += abs(signed_area(*triangle))
            cells.update(triangle_cells(triangle))
        for cell in cells:
            if counts[cell] < 2:
                counts[cell] += 1
    covered = sum(1 for value in counts if value > 0)
    overlapped = sum(1 for value in counts if value > 1)
    return covered, overlapped, outside, area


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
