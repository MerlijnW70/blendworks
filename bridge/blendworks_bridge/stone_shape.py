"""Stone shapes: hull, resampling and roundness."""

import math

import bpy
import numpy

from .registry import COMMANDS
from .schema import validate
from .util import get_mesh_object

NOTE_9 = "Shapes of stones by how far water has moved them. A fresh fragment is angular: a block of random proportions broken into flat-faced cells (fracture, Voronoi) whose corners are knocked off by planar chips (chip). Rolling and sliding in water wears corners and edges first (abrade), so the stone a flood has carried a long way has been through more passes of wear, and rounding comes fast at first and then slowly (Kuenen 1956, Experimental abrasion of pebbles 2, rolling by current; Krumbein 1941, Measurement and geological significance of shape and roundness of sedimentary particles). Transport 0 is a fresh fragment, 1 a stone worked for PASSES passes of the most wear abrade allows (a tenth of its volume each). The surface of every stone then gets a little relief from a noise of the grain of the rock (RELIEF of its size at a wavelength of GRAIN of it), because no stone is smooth."
OUTLINE_POINTS = 240
CURVATURE_SPAN = 4
CORNER_SHARE = 0.1
CHIPS = 6
CHIP_DEPTH = 0.16
LONG_AXIS = 1.0
INTERMEDIATE = (0.5, 0.95)
SHORT = (0.3, 0.7)
PIECES = 4
PASSES = 6
EDGE_DIVISOR = 10.0
SHARP_ANGLE = 35.0
RELIEF = 0.02
GRAIN = 0.3


def mesh_arrays(obj):
    """Vertices (n, 3) in the object's own space and triangles (m, 3) of a mesh object."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    points = numpy.zeros(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", points)
    triangles = numpy.zeros(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
    mesh.loop_triangles.foreach_get("vertices", triangles)
    return points.reshape(-1, 3), triangles.reshape(-1, 3)


def volume(points, triangles):
    a, b, c = points[triangles[:, 0]], points[triangles[:, 1]], points[triangles[:, 2]]
    return abs(float(numpy.einsum("ij,ij->i", a, numpy.cross(b, c)).sum()) / 6.0)


def hull(xy):
    """Convex hull of plane points, counter-clockwise (Andrew's monotone chain)."""
    order = numpy.lexsort((xy[:, 1], xy[:, 0]))
    points = [tuple(row) for row in xy[order].tolist()]
    chains = []
    for sequence in (points, points[::-1]):
        chain = []
        for point in sequence:
            while len(chain) >= 2 and (chain[-1][0] - chain[-2][0]) * (point[1] - chain[-2][1]) - (chain[-1][1] - chain[-2][1]) * (point[0] - chain[-2][0]) <= 0.0:
                chain.pop()
            chain.append(point)
        chains.append(chain[:-1])
    return numpy.array(chains[0] + chains[1])


def resampled(outline, count):
    """The closed outline at count points equally far apart along it."""
    closed = numpy.vstack([outline, outline[:1]])
    lengths = numpy.concatenate([[0.0], numpy.cumsum(numpy.linalg.norm(numpy.diff(closed, axis=0), axis=1))])
    where = numpy.linspace(0.0, lengths[-1], count, endpoint=False)
    return numpy.column_stack([numpy.interp(where, lengths, closed[:, axis]) for axis in range(2)]), lengths[-1]


def roundness(points):
    """Roundness in 0..1 of a stone lying on its short axis, after Wadell (1932) and Krumbein (1941): the mean radius of curvature
    of the corners of its outline seen from above over the radius of a circle of the same area. The outline is the convex
    hull of the vertices seen from above, set at OUTLINE_POINTS equal steps; the curvature at a point is the turn of its
    path over the CURVATURE_SPAN steps either side of it divided by their length; the corners are the CORNER_SHARE sharpest
    points. A circle reads 1, a square about 0.2, a stone with its corners worn off in between."""
    outline, perimeter = resampled(hull(points[:, :2]), OUTLINE_POINTS)
    span = CURVATURE_SPAN
    before = outline - numpy.roll(outline, span, axis=0)
    after = numpy.roll(outline, -span, axis=0) - outline
    turn = numpy.abs(numpy.arctan2(before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0], numpy.einsum("ij,ij->i", before, after)))
    radius = (span * perimeter / OUTLINE_POINTS) / numpy.maximum(turn, 1e-9)
    area = 0.5 * abs(float(numpy.dot(outline[:, 0], numpy.roll(outline[:, 1], -1)) - numpy.dot(outline[:, 1], numpy.roll(outline[:, 0], -1))))
    sharp = numpy.sort(radius)[: max(1, int(round(CORNER_SHARE * OUTLINE_POINTS)))]
    return min(1.0, float(sharp.mean()) / math.sqrt(area / math.pi))


def run(ctx, command, **args):
    entry = COMMANDS[command]
    return entry.run(ctx, validate(entry.schema, args))


def normalise(obj):
    """Scale a stone so its longest side is one metre, centre it over the origin and stand its lowest point on it."""
    points, _ = mesh_arrays(obj)
    low, high = points.min(axis=0), points.max(axis=0)
    centre = 0.5 * (low + high)
    shifted = (points - centre) / max(float((high - low).max()), 1e-9)
    shifted[:, 2] -= shifted[:, 2].min()
    obj.data.vertices.foreach_set("co", shifted.ravel())
    obj.data.update()
    return float(shifted[:, 2].max())


def build_stone(ctx, name, transport, seed, material=None):
    """One stone: a block of random proportions broken into Voronoi cells (flat-faced convex fragments), the biggest chipped
    (more for a fresh fragment) and then abraded in passes (more for a stone water has worked long). The mesh has its
    longest side one metre and rests on its lowest point at the origin, ready to place at any size."""
    rng = numpy.random.default_rng([seed, 0x570E])
    ratios = [LONG_AXIS, rng.uniform(*INTERMEDIATE), 0.0]
    ratios[2] = ratios[1] * rng.uniform(*SHORT)
    run(ctx, "add_primitive", type="cube", name=name, size=1.0)
    run(ctx, "transform", name=name, scale=ratios, rotation=[0.0, 0.0, float(rng.uniform(0.0, 180.0))])
    run(ctx, "apply_transform", name=name, location=True, rotation=True, scale=True)
    pieces = run(ctx, "fracture", name=name, pieces=PIECES, mode="voronoi", seed=int(rng.integers(1 << 30)), min_size=0.05)["pieces"]
    biggest = max((get_mesh_object(piece) for piece in pieces), key=lambda piece: volume(*mesh_arrays(piece)))
    for piece in pieces:
        if piece != biggest.name:
            bpy.data.objects.remove(bpy.data.objects[piece])
    biggest.name = name
    extent = float(max(biggest.dimensions))
    run(ctx, "chip", name=name, count=CHIPS, depth=CHIP_DEPTH * extent, seed=int(rng.integers(1 << 30)))
    passes = int(round(PASSES * transport))
    for index in range(max(passes, 1)):
        run(ctx, "abrade", name=name, amount=1.0 if passes else 0.0, seed=int(rng.integers(1 << 30)), edge_length=extent / EDGE_DIVISOR)
    run(ctx, "noise_displace", name=name, amplitude=RELIEF * extent, scale=GRAIN * extent, octaves=3, hurst=0.6, seed=int(rng.integers(1 << 30)))
    height = normalise(biggest)
    run(ctx, "uv_smart_project", name=name)
    if material is not None:
        biggest.data.materials.clear()
        biggest.data.materials.append(bpy.data.materials[material])
        biggest.data.polygons.foreach_set("material_index", numpy.zeros(len(biggest.data.polygons), dtype=numpy.int32))
    biggest.data.polygons.foreach_set("use_smooth", numpy.ones(len(biggest.data.polygons), dtype=bool))
    biggest.data.set_sharp_from_angle(angle=math.radians(SHARP_ANGLE))
    return biggest, height
