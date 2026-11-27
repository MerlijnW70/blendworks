import math

from mathutils import Vector

from .errors import bad_args
from .meshdata import MeshData
from .outlines import (
    clockwise,
    counter_clockwise,
    drop_repeats,
    edge_directions_kept,
    offset_loop,
    require_holes_inside,
    require_simple,
    signed_area,
    triangulate,
)
from .skin import skin
from .util import check_vertex_cap


def level_table(depth, chamfer, segments):
    if chamfer <= 0:
        return [(0.0, 0.0), (0.0, depth)]
    if depth < 2 * chamfer * (1 - 1e-9):
        raise bad_args("the chamfer is more than half the depth")
    bottom = []
    for step in range(segments + 1):
        angle = math.pi / 2 * step / segments
        bottom.append((chamfer * (1 - math.sin(angle)), chamfer * (1 - math.cos(angle))))
    top = [(inset, depth - z) for inset, z in reversed(bottom)]
    levels = bottom + top
    cleaned = [levels[0]]
    for level in levels[1:]:
        if abs(level[0] - cleaned[-1][0]) > 1e-12 or abs(level[1] - cleaned[-1][1]) > 1e-12:
            cleaned.append(level)
    return cleaned


def inset_loops(loops, inset):
    if inset == 0:
        return loops
    moved = [offset_loop(loop, inset) for loop in loops]
    for before, after in zip(loops, moved):
        if not edge_directions_kept(before, after):
            raise bad_args("the chamfer is too large for this outline")
    require_simple(moved, "the chamfered outline")
    return moved


def checked(points, what):
    cleaned = drop_repeats(points, what)
    if abs(signed_area(cleaned)) < 1e-14:
        raise bad_args(f"{what} encloses no area")
    return cleaned


def prepare_loops(outline, holes):
    outer = counter_clockwise(checked(outline, "the outline"))
    cleaned = [clockwise(checked(hole, f"hole {index}")) for index, hole in enumerate(holes)]
    require_simple([outer] + cleaned, "the outline and its holes")
    require_holes_inside(outer, cleaned)
    return [outer] + cleaned


def cap_faces(data, loops, rings, z, top):
    flat, triangles = triangulate(loops[0], loops[1:])
    indices = [index for ring in rings for index in ring]
    island = data.island_count()
    for a, b, c in triangles:
        corner = (a, b, c) if top else (a, c, b)
        uvs = [(flat[i][0] if top else -flat[i][0], flat[i][1]) for i in corner]
        data.face([indices[i] for i in corner], uvs, island, 0, False)


def check_extrusion(loops, levels):
    """Exact: skin makes one vertex per loop point on every level, inset loops keep their point count, caps add none."""
    check_vertex_cap(sum(len(loop) for loop in loops) * len(levels))


def extrusion_data(outline, holes, depth, chamfer, segments, centered, caps=True):
    loops = prepare_loops(outline, holes)
    levels = level_table(depth, chamfer, segments)
    check_extrusion(loops, levels)
    offset = -depth / 2.0 if centered else 0.0
    cache = {}
    for inset, _ in levels:
        key = round(inset, 12)
        if key not in cache:
            cache[key] = inset_loops(loops, inset)
    data = MeshData()
    stacks = []
    for loop_index in range(len(loops)):
        rings = [[Vector((x, y, z + offset)) for x, y in cache[round(inset, 12)][loop_index]] for inset, z in levels]
        stacks.append(skin(data, rings, island=data.island_count(), smooth=True))
    if caps:
        cap_faces(data, cache[round(levels[0][0], 12)], [stack[0] for stack in stacks], levels[0][1] + offset, False)
        cap_faces(data, cache[round(levels[-1][0], 12)], [stack[-1] for stack in stacks], levels[-1][1] + offset, True)
    return data
