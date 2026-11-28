"""Shapes of stones by how far water has moved them (rock_shape holds the measures, classes and sources).

A stone starts as an inner cell of a block broken into Voronoi cells by fracture, so its faces are joints and breaks at
random angles, not the faces of a box, about six of them (Domokos et al. 2020); on a talus block half of them are fresh. The cell is turned into its own axes and
stretched to proportions drawn from its history class, which keeps every face flat. chip knocks pieces off its edges and
corners: fresh fracture faces, with the rock's fresh material. abrade then wears it in passes, edges and corners first by
their curvature, until its Wadell roundness reaches the target of its transport; a talus block gets none. A river cobble's
chips are worn away with the rest, so it has no fresh faces left. Fresh faces of fine-grained, brittle rock (basalt,
limestone) are dished like conchoidal breaks. A little relief at the scale of the stone (RELIEF of it) follows; the grain,
pits and cracks come from the rock material at render time.
"""
import math

import bpy
import numpy

from . import rock_lithology, rock_shape
from .fragments import fresh_material
from .noise_stack import stack_field
from .registry import COMMANDS
from .rock_fresh import FRESH_FLAG, fresh_variant, rock_params
from .rock_relief import is_rock_material
from .schema import validate
from .util import get_mesh_object

PIECES = 10
FRESH_CELL_SHARE = 0.3
PASS_WEAR = 0.1
MAX_PASSES = 10
EDGE_DIVISOR = 14.0
SHARP_ANGLE = 35.0
RELIEF = 0.008
BREAK_ROUGHNESS = 0.012
BREAK_FIELD = {"basis": "perlin", "scale": 0.08, "octaves": 4, "lacunarity": 2.0, "hurst": 0.55, "mode": "ridged", "ridge_offset": 1.0, "warp": 0.0, "warp_octaves": 1}
GRAIN = 0.25


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


def roundness(points):
    """Wadell roundness of a stone lying on its short axis, seen from above (rock_shape.roundness)."""
    return rock_shape.roundness(points)


def shape_of(obj):
    return rock_shape.shape_report(*mesh_arrays(obj))


def run(ctx, command, **args):
    entry = COMMANDS[command]
    return entry.run(ctx, validate(entry.schema, args))


def set_points(obj, points):
    obj.data.vertices.foreach_set("co", numpy.asarray(points, dtype=numpy.float64).ravel())
    obj.data.update()


def normalise(obj):
    """Scale a stone so its longest side is one metre, centre it over the origin and stand its lowest point on it."""
    points, _ = mesh_arrays(obj)
    low, high = points.min(axis=0), points.max(axis=0)
    centre = 0.5 * (low + high)
    shifted = (points - centre) / max(float((high - low).max()), 1e-9)
    shifted[:, 2] -= shifted[:, 2].min()
    set_points(obj, shifted)
    return float(shifted[:, 2].max())


def face_flags(mesh):
    slots = numpy.zeros(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("material_index", slots)
    fresh = numpy.array([material is not None and bool(material.get(FRESH_FLAG)) for material in mesh.materials] or [False])
    return fresh[numpy.minimum(slots, len(fresh) - 1)]


def cut_share(piece):
    """Share of a piece's area on the faces the fracture cut (its fresh slot): an inner cell has no face of the block."""
    mesh = piece.data
    areas = numpy.zeros(len(mesh.polygons))
    mesh.polygons.foreach_get("area", areas)
    return float(areas[face_flags(mesh)].sum() / max(areas.sum(), 1e-12))


def inner_cell(ctx, name, rng):
    """The Voronoi cell of a unit block with the most of its surface on cut faces, among the cells of at least
    FRESH_CELL_SHARE of the biggest's volume; the others are removed."""
    run(ctx, "add_primitive", type="cube", name=name, size=1.0)
    pieces = [get_mesh_object(piece) for piece in run(ctx, "fracture", name=name, pieces=PIECES, mode="voronoi", seed=int(rng.integers(1 << 30)), min_size=0.04)["pieces"]]
    volumes = {piece.name: volume(*mesh_arrays(piece)) for piece in pieces}
    biggest = max(volumes.values())
    chosen = max((piece for piece in pieces if volumes[piece.name] >= FRESH_CELL_SHARE * biggest), key=lambda piece: (cut_share(piece), volumes[piece.name]))
    for piece in pieces:
        if piece != chosen:
            mesh = piece.data
            bpy.data.objects.remove(piece)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    chosen.name = name
    return chosen


def proportioned(obj, history, rng):
    """Turn the cell into its own axes (long along x, short along z) and stretch it to a long side of one and the drawn
    intermediate and short ratios; an affine map keeps every face flat."""
    points, triangles = mesh_arrays(obj)
    axes, spans, middle = rock_shape.principal_axes(points, triangles)
    if numpy.linalg.det(axes) < 0.0:
        axes[:, 2] = -axes[:, 2]
    intermediate = rng.uniform(*history["intermediate"])
    short = intermediate * rng.uniform(*history["short"])
    set_points(obj, ((points - middle) @ axes) * (numpy.array([1.0, intermediate, short]) / spans))


def only_slot(obj, material):
    mesh = obj.data
    mesh.materials.clear()
    if material is not None:
        mesh.materials.append(material)
    mesh.polygons.foreach_set("material_index", numpy.zeros(len(mesh.polygons), dtype=numpy.int32))


def keep_fresh(obj, main, chosen):
    """Give the main material to every face but the chosen ones, which keep a fresh slot (the rock's fresh variant)."""
    only_slot(obj, main)
    if main is None or not chosen.any():
        return
    obj.data.materials.append(fresh_variant(main) if is_rock_material(main) else fresh_material())
    obj.data.polygons.foreach_set("material_index", chosen.astype(numpy.int32))


def assign_slots(obj, main, fresh_kept):
    """The stone's slots: its material and, where fresh faces stay, the fresh material (the rock's fresh variant); fresh
    faces worn away join the main slot. Returns which faces stay fresh."""
    mesh = obj.data
    is_fresh = face_flags(mesh) & fresh_kept & (main is not None)
    keep_fresh(obj, main, is_fresh)
    return is_fresh


def rough_breaks(obj, is_fresh, depth_share, seed):
    """Make each fresh face a rough break, not a clean cut: its inner vertices move off its plane by a ridged noise of
    BREAK_ROUGHNESS (a hackly fracture surface), and for brittle fine-grained rock sink as a conchoidal dish by depth_share of
    its radius times (1 - (d / R)^2), d from the centre of its rim; the rim, shared with the weathered faces, stays."""
    if not is_fresh.any():
        return
    mesh = obj.data
    points, _ = mesh_arrays(obj)
    faces = [list(polygon.vertices) for polygon in mesh.polygons]
    rim = set()
    for index, face in enumerate(faces):
        if not is_fresh[index]:
            rim.update(face)
    normals = numpy.zeros(len(faces) * 3)
    mesh.polygons.foreach_get("normal", normals)
    normals = normals.reshape(-1, 3)
    groups = {}
    for index in numpy.nonzero(is_fresh)[0].tolist():
        groups.setdefault(tuple(numpy.round(normals[index], 2).tolist()), set()).update(faces[index])
    moved = points.copy()
    for key, members in sorted(groups.items()):
        inner, ring = sorted(members - rim), sorted(members & rim)
        if not inner or len(ring) < 3:
            continue
        centre = points[ring].mean(axis=0)
        radius = float(numpy.linalg.norm(points[ring] - centre, axis=1).max())
        distance = numpy.linalg.norm(points[inner] - centre, axis=1)
        taper = numpy.clip(1.0 - (distance / max(radius, 1e-9)) ** 2, 0.0, 1.0)
        hackly = BREAK_ROUGHNESS * stack_field(points[inner], {**BREAK_FIELD, "seed": seed})
        sink = depth_share * radius * taper + hackly * numpy.sqrt(taper)
        moved[inner] -= numpy.array(key)[None, :] * sink[:, None]
    set_points(obj, moved)


def lithology_of(material):
    return rock_params(material).get("lithology", "granite") if is_rock_material(material) else "granite"


def build_stone(ctx, name, transport, seed, material=None):
    """One stone of a transport from 0 (a fresh fragment) to 1 (a long-rolled cobble): an inner Voronoi cell of a block,
    proportioned for its history class, chipped, abraded until its roundness reaches the class target, its surviving fresh
    faces dished by the rock's conchoidal share and given a little relief. The mesh has its longest side one metre and
    rests on its lowest point at the origin, ready to place at any size. Returns the object, its height and its shape."""
    rng = numpy.random.default_rng([seed, 0x570E])
    history_name = rock_shape.history_of(transport)
    history = rock_shape.HISTORIES[history_name]
    main = bpy.data.materials.get(material) if material is not None else None
    stone = inner_cell(ctx, name, rng)
    proportioned(stone, history, rng)
    cut = face_flags(stone.data)
    keep_fresh(stone, main, cut & (rng.uniform(size=len(cut)) < history["fresh_faces"]))
    run(ctx, "chip", name=name, count=history["chips"], depth=history["chip_depth"], seed=int(rng.integers(1 << 30)))
    edge = 1.0 / EDGE_DIVISOR
    run(ctx, "abrade", name=name, amount=0.0, edge_length=edge)
    target, passes = rock_shape.target_roundness(transport), 0
    while passes < MAX_PASSES and shape_of(stone)["roundness"] < target:
        run(ctx, "abrade", name=name, amount=PASS_WEAR, seed=int(rng.integers(1 << 30)), edge_length=edge)
        passes += 1
    is_fresh = assign_slots(stone, main, history["fresh"])
    rough_breaks(stone, is_fresh, rock_lithology.lithology(lithology_of(main))["conchoidal"], int(rng.integers(1 << 30)))
    run(ctx, "noise_displace", name=name, amplitude=RELIEF, scale=GRAIN, octaves=5, hurst=0.5, seed=int(rng.integers(1 << 30)))
    height = normalise(stone)
    run(ctx, "uv_smart_project", name=name)
    stone.data.polygons.foreach_set("use_smooth", numpy.ones(len(stone.data.polygons), dtype=bool))
    stone.data.set_sharp_from_angle(angle=math.radians(SHARP_ANGLE))
    report = shape_of(stone)
    report.update({"history": history_name, "target_roundness": target, "passes": passes, "fresh_share": float(is_fresh.mean())})
    return stone, height, report
