"""The distant_land command: land that surrounds a region out to tens of kilometres and continues its terrain."""

import json
import math

import bpy
import numpy

from .. import land_material, land_stats
from ..edge_order import canonical_edges
from ..errors import bad_args
from ..land_border import BorderCorrection
from ..land_field import STYLES, LandField, earth_drop, smoothstep
from ..camera_reach import raise_all
from ..land_region import Region, region_material, uv_affine
from ..land_rings import Rect, RingMesh, estimate_triangles
from ..liquid_world import write_point_attribute
from ..limits import FRACTION, MAX_COORDINATE, MAX_LENGTH, MAX_SEED
from ..limits_land import (BORDER_TOLERANCE, DEFAULT_LAND_TRIANGLES, EARTH_RADIUS, LAND_TRIANGLE_BYTES, LEAST_LAND_DETAIL,
                           LEAST_BEHIND, LEAST_LAND_DISTANCE, LEAST_PLANET_RADIUS, MAX_BEHIND, MAX_LAND_DETAIL, MAX_LAND_TRIANGLES,
                           MAX_PLANET_RADIUS, MAX_RANGE_HEIGHT)
from ..registry import command
from ..schema import CREATES, EXISTS, boolean, color, integer, names, number, obj, point2, ref, string
from ..util import get_object, link_object, require_free_name, rounded

PROPERTY = "blendworks_distant_land"
DEFAULT_NAME = "DistantLand"
VIEW_MARGIN = math.radians(12.0)
BUDGET_STEP = 0.85
RANGE_REACH = 5_000.0
LEAST_RANGE = 800.0
BROADEST_REACH = 40_000.0
SAMPLE_OFFSET = 7.0
CHECK_POINTS = 2000

BOUNDS = obj({"min": point2("Lowest corner [x, y] in metres."), "max": point2("Highest corner [x, y] in metres.")}, ["min", "max"])
BOUNDS["description"] = "Region rectangle; needs ground. Default: the terrain's extent seen from above."


def plan_distant_land(args, state):
    state.add("object", args["name"])
    state.add("material", args["name"] + "_ground")


@command(
    "distant_land",
    "Surround a region with land out to 80 km or more that continues its measured character: rolling hills or ranges behind ranges, LOD rings, earth curvature.",
    {
        "name": ref(string("New object for the land; must be unused.", default=DEFAULT_NAME), "object", CREATES),
        "terrain": ref(names("Terrain objects that make up the region; their extent is the region rectangle."), "object"),
        "bounds": BOUNDS,
        "ground": ref(string("bounds: the object whose surface gives the heights in the rectangle."), "object", EXISTS),
        "distance": number("How far the land reaches past the region on every side, in metres.", LEAST_LAND_DISTANCE, MAX_LENGTH, 100_000.0),
        "style": string("rolling: the region's hills on and on; ranges: mountain ranges rising behind each other with distance.", list(STYLES), "rolling"),
        "range_height": number("ranges: height in metres the farthest ranges rise above the land. Default: from the region's relief, at least 800 m.", 0.0, MAX_RANGE_HEIGHT),
        "seed": integer("Random seed; the same seed gives the same land.", 0, MAX_SEED, 0),
        "detail": integer("Vertices across each ring's inner half size; the vertex spacing doubles from ring to ring.", LEAST_LAND_DETAIL, MAX_LAND_DETAIL, 128),
        "behind": number("Land out of the camera's view has vertices this many times farther apart along each ring.", LEAST_BEHIND, MAX_BEHIND, 4.0),
        "budget": integer("Most triangles; detail is lowered until the land fits.", 1, MAX_LAND_TRIANGLES, DEFAULT_LAND_TRIANGLES),
        "curvature": boolean("Let the land fall away with the curvature of the earth.", True),
        "earth_radius": number("Radius of the earth in metres for the curvature.", LEAST_PLANET_RADIUS, MAX_PLANET_RADIUS, EARTH_RADIUS),
        "water_level": number("Ground of the region below this height counts as water, besides the scene's liquids.", -MAX_COORDINATE, MAX_COORDINATE),
        "camera": ref(string("Camera whose view gets the full detail. Default: the active camera; without one every side does."), "object", EXISTS),
        "material": ref(string("Material the ground continues. Default: the region's first material."), "material", EXISTS),
        "rock_color": color("Colour of steep ground far out, linear RGB.", list(land_material.DEFAULT_ROCK), allow_alpha=False),
        "variation": number("Broad variation of the ground's tone far out: 0 none, 0.3 strong.", 0.0, FRACTION, 0.18),
    },
    plan=plan_distant_land,
    slow=True,
    family="shapes",
    intents=("land to the horizon around a scene", "distant mountains behind the valley", "hills fading into the distance",
             "terrain out to 100 km with earth curvature"),
    nearest=(("heightfield", "for terrain tiles of the region itself"), ("distant_forest", "to put forest on it"), ("atmosphere", "for the haze that makes it fade")),
)
def distant_land(ctx, args):
    require_free_name(args["name"])
    region = measured_region(ctx, args)
    rect = Rect(region.low, region.high)
    check_reach(rect, args["distance"])
    heights, wet, valid, grid_spacing = region.grid()
    stats = land_stats.statistics(heights, grid_spacing, wet, valid)
    size = float(max(region.size()))
    style = args["style"]
    range_height = args.get("range_height", min(MAX_RANGE_HEIGHT, max(LEAST_RANGE, 6.0 * stats["range"])))
    fine_reach = max(4.0 * region.spacing, 0.5 * stats["dominant_wavelength"], 2.0 * rect.rho0 / args["detail"])
    field = LandField(stats, style, args["seed"], size, range_height, fine_reach, RANGE_REACH)
    land = field.calibrate(heights.shape, grid_spacing, (rect.centre[0] + SAMPLE_OFFSET * size, rect.centre[1]))
    border_spacing = min(region.spacing, size / 64.0)
    sides = region.border_sides(border_spacing)
    view = camera_view(ctx, args)
    detail = fit_budget(rect, sides, args, view)
    rings = RingMesh(rect, sides, args["distance"], detail, view, args["behind"])
    radius = args["earth_radius"] if args["curvature"] else None
    surface = LandSurface(region, rect, field, stats["mean"], radius)
    reaches = (fine_reach, min(BROADEST_REACH, max(1.5 * size, 2.0 * fine_reach)), fine_reach)
    z, water, correction = surface.heights(rings, reaches, size / 8.0)
    obj = build_object(ctx, args, region, rings, z, water, reaches[0])
    material, continued = land_material.ground_material(args["name"] + "_ground", chosen_material(args, region),
                                                        args["rock_color"], args["variation"])
    obj.data.materials.append(material)
    clipped = raise_all(ctx.scene, ctx.view_layer)
    settings = {"rect": [list(region.low), list(region.high)], "distance": args["distance"], "fine_reach": reaches[0],
                "earth_radius": radius, "style": style, "seed": args["seed"], "spacing": region.spacing,
                "dominant_wavelength": stats["dominant_wavelength"], "relief": stats["relief"]}
    obj[PROPERTY] = json.dumps(settings)
    triangles = len(rings.faces)
    return {
        "name": obj.name,
        "material": material.name,
        "continues_material": continued,
        "vertices": len(rings.xy),
        "triangles": triangles,
        "budget": {"triangles": args["budget"], "memory_bytes": triangles * LAND_TRIANGLE_BYTES.plain(),
                   "bytes_per_triangle": LAND_TRIANGLE_BYTES.plain(), "detail": detail, "asked_detail": args["detail"]},
        "rings": ring_report(rect, rings, args["distance"], detail),
        "distance": args["distance"],
        "region": {"min": [rounded(v) for v in region.low], "max": [rounded(v) for v in region.high],
                   "spacing": rounded(region.spacing), "objects": [item.name for item in region.objects]},
        "border": border_error(region, obj, rings),
        "statistics": {"region": brief(stats), "land": brief(land), "comparison": {k: rounded(v, 4) for k, v in land_stats.compare(stats, land).items()}},
        "field": field.describe(),
        "correction": correction,
        "curvature": curvature_report(radius, args["distance"], size),
        "height_range": [rounded(float(z.min()), 3), rounded(float(z.max()), 3)],
        "water_share": rounded(float((water >= 0.5).mean()), 4),
        "cameras": clipped,
    }


def measured_region(ctx, args):
    terrain = args.get("terrain")
    bounds = args.get("bounds")
    ground = args.get("ground")
    if (terrain is None) == (bounds is None):
        raise bad_args("give terrain, or bounds with ground")
    if bounds is not None and ground is None:
        raise bad_args("bounds needs ground: the object whose surface gives the heights")
    if terrain is not None and ground is not None:
        raise bad_args("ground goes with bounds; terrain objects give their own heights")
    if bounds is not None and any(low >= high for low, high in zip(bounds["min"], bounds["max"])):
        raise bad_args("bounds.min must be below bounds.max on both axes")
    objects = [get_object(name) for name in (terrain or [ground])]
    for item in objects:
        if item.type != "MESH":
            raise bad_args(f"{item.name} is not a mesh")
    return Region(ctx, terrain=objects if terrain else None, bounds=bounds, ground=objects[0] if ground else None,
                  water_level=args.get("water_level"))


def check_reach(rect, distance):
    far = max(abs(rect.x0 - distance), abs(rect.x1 + distance), abs(rect.y0 - distance), abs(rect.y1 + distance))
    if far > MAX_COORDINATE:
        raise bad_args(f"the land would reach {far:g} m from the origin, past the coordinate limit {MAX_COORDINATE.plain():g} m "
                       f"({MAX_COORDINATE.reason}); give a shorter distance or move the region towards the origin")


def camera_view(ctx, args):
    camera = get_object(args["camera"]) if "camera" in args else ctx.scene.camera
    if camera is None or camera.type != "CAMERA":
        if "camera" in args:
            raise bad_args(f"{args['camera']} is not a camera")
        return None
    matrix = camera.matrix_world
    forward = -numpy.array(matrix.to_3x3().col[2])
    flat = numpy.array([forward[0], forward[1]])
    if numpy.linalg.norm(flat) < 0.2:
        return None
    data = camera.data
    scene = ctx.scene
    aspect = scene.render.resolution_x / max(scene.render.resolution_y, 1)
    width = data.sensor_width if data.sensor_fit != "VERTICAL" else data.sensor_height * aspect
    half = math.atan(width / (2.0 * data.lens)) if data.type == "PERSP" else math.radians(30.0)
    return (numpy.array(matrix.translation)[:2], flat / numpy.linalg.norm(flat), half + VIEW_MARGIN)


def fit_budget(rect, sides, args, view):
    border = sum(len(side) - 1 for side in sides)
    detail = args["detail"]
    while True:
        triangles = estimate_triangles(rect, border, args["distance"], detail, view, args["behind"])
        if triangles <= args["budget"]:
            return detail
        if detail <= LEAST_LAND_DETAIL:
            raise bad_args(f"even at detail {LEAST_LAND_DETAIL.plain()} the land needs {triangles} triangles, over the budget "
                           f"{args['budget']}; raise budget or behind")
        detail = max(LEAST_LAND_DETAIL.plain(), int(detail * BUDGET_STEP))


def chosen_material(args, region):
    if "material" in args:
        return bpy.data.materials[args["material"]]
    return region_material(region.objects)


class LandSurface:
    def __init__(self, region, rect, field, mean, radius):
        self.region, self.rect, self.field, self.mean, self.radius = region, rect, field, mean, radius

    def synthesized(self, xy, spacing):
        heights, water = self.field.evaluate(xy, spacing, self.rect.distance(xy))
        return self.mean + heights - earth_drop(xy, self.rect.centre, self.radius), water

    def heights(self, rings, reaches, smooth_length):
        border = rings.xy[: rings.border_count]
        spacing = rings.spacing[: rings.border_count]
        top, wet = self.region.surface_heights(self.region.inward(border))
        synthesized_border, _ = self.synthesized(border, spacing)
        top = numpy.where(numpy.isnan(top), synthesized_border, top)
        normals = outward_normals(self.rect, border)
        step = max(self.region.spacing, 0.5)
        inner, _ = self.region.surface_heights(border - normals * step)
        inner = numpy.where(numpy.isnan(inner), top, inner)
        outer, _ = self.synthesized(border + normals * step, spacing)
        slope_gap = (top - inner) / step - (outer - synthesized_border) / step
        correction = BorderCorrection(self.rect, border, top - synthesized_border, slope_gap, wet.astype(float), reaches, smooth_length)
        z, water = self.synthesized(rings.xy, rings.spacing)
        added, border_water = correction.apply(rings.xy)
        z = z + added
        water = numpy.maximum(water, border_water)
        z[: rings.border_count] = top
        water[: rings.border_count] = wet
        return z, water, correction.describe()


def outward_normals(rect, xy):
    normals = numpy.zeros_like(xy)
    normals[:, 0] = numpy.where(numpy.isclose(xy[:, 0], rect.x0, rtol=0.0, atol=1e-6), -1.0, 0.0) + numpy.where(numpy.isclose(xy[:, 0], rect.x1, rtol=0.0, atol=1e-6), 1.0, 0.0)
    normals[:, 1] = numpy.where(numpy.isclose(xy[:, 1], rect.y0, rtol=0.0, atol=1e-6), -1.0, 0.0) + numpy.where(numpy.isclose(xy[:, 1], rect.y1, rtol=0.0, atol=1e-6), 1.0, 0.0)
    return normals / numpy.maximum(numpy.linalg.norm(normals, axis=1, keepdims=True), 1e-9)


def build_object(ctx, args, region, rings, z, water, fine_reach):
    origin = numpy.array(region.objects[0].matrix_world.translation)
    points = numpy.column_stack([rings.xy, z]) - origin[None, :]
    mesh = bpy.data.meshes.new(args["name"])
    mesh.vertices.add(len(points))
    mesh.vertices.foreach_set("co", points.astype(numpy.float32).ravel())
    faces = rings.faces.astype(numpy.int32)
    mesh.loops.add(faces.size)
    mesh.polygons.add(len(faces))
    mesh.loops.foreach_set("vertex_index", faces.ravel())
    mesh.polygons.foreach_set("loop_start", numpy.arange(0, faces.size, 3, dtype=numpy.int32))
    mesh.polygons.foreach_set("loop_total", numpy.full(len(faces), 3, dtype=numpy.int32))
    mesh.polygons.foreach_set("use_smooth", numpy.ones(len(faces), dtype=bool))
    mesh.update(calc_edges=True)
    canonical_edges(mesh)
    affine = uv_affine(region.objects[0])
    uv_points = rings.xy if affine is None else numpy.column_stack([rings.xy, numpy.ones(len(rings.xy))]) @ affine
    layer = mesh.uv_layers.new(name="UVMap")
    layer.uv.foreach_set("vector", uv_points[faces.ravel()].astype(numpy.float32).ravel())
    distance = Rect(region.low, region.high).distance(rings.xy)
    write_point_attribute(mesh, land_material.WATER_ATTRIBUTE, water)
    write_point_attribute(mesh, land_material.FAR_ATTRIBUTE, smoothstep(0.0, 2.0 * fine_reach, distance))
    write_point_attribute(mesh, "dl_distance", distance)
    mesh.update()
    obj = link_object(ctx, args["name"], mesh)
    obj.location = tuple(float(value) for value in origin)
    ctx.view_layer.update()
    return obj


def ring_report(rect, rings, distance, detail):
    spacings = sorted({round(float(value), 3) for value in rings.spacing[rings.border_count:]})
    return {"count": len(spacings), "loops": rings.loop_count, "detail": detail, "spacings": spacings[:32],
            "inner_half_size": rounded(rect.rho0, 3), "outer_offset": distance}


def border_error(region, obj, rings):
    """Largest height gap at the border, measured between border vertices, where the region's own surface lies."""
    count = rings.border_count
    border = rings.xy[:count]
    following = numpy.roll(numpy.arange(count), -1)
    mesh = obj.data
    local = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
    mesh.vertices.foreach_get("co", local)
    z = local.reshape(-1, 3)[:count, 2].astype(numpy.float64) + obj.matrix_world.translation.z
    fractions = numpy.linspace(0.0, 1.0, 5)[1:-1]
    chosen = numpy.arange(0, count, max(1, count // CHECK_POINTS))
    points = (border[chosen, None, :] * (1.0 - fractions[None, :, None]) + border[following[chosen], None, :] * fractions[None, :, None]).reshape(-1, 2)
    land = (z[chosen, None] * (1.0 - fractions[None, :]) + z[following[chosen], None] * fractions[None, :]).ravel()
    surface, _ = region.surface_heights(region.inward(points))
    gap = numpy.abs(surface - land)
    gap = gap[~numpy.isnan(gap)]
    largest = float(gap.max()) if len(gap) else 0.0
    return {"max_gap": rounded(largest, 5), "tolerance": BORDER_TOLERANCE.plain(), "within": largest <= BORDER_TOLERANCE.plain(),
            "vertices": count, "checked": int(len(gap))}


def brief(stats):
    keys = ("mean", "relief", "range", "slope", "dominant_wavelength", "hurst", "water_share", "water_size", "flat_share", "flat_size")
    return {key: ([rounded(v, 4) for v in stats[key]] if isinstance(stats[key], list) else rounded(stats[key], 4)) for key in keys}


def curvature_report(radius, distance, size):
    if radius is None:
        return None
    far = distance + size / 2.0
    return {"radius": radius, "drop_at_distance": rounded(radius - math.sqrt(radius * radius - far * far), 3), "measured_from": "region centre"}
