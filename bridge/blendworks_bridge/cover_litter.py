import math

import bmesh
import numpy

from .cover_mesh import ElementMesh, unit

CARD_LIFT = 0.0008
TWIG_SHAPES = ((6, 5), (5, 4), (4, 4), (4, 3), (3, 3), (3, 2))
LEAF_GRIDS = ((5, 8), (5, 6), (3, 6), (3, 4), (3, 3))
PEBBLE_LEVELS = (3, 2, 1)


def twig_axes(p, rng):
    length = rng.uniform(p["length"][0], p["length"][1])
    radius = p["thickness"] * rng.uniform(0.75, 1.25)
    heading = rng.uniform(-0.15, 0.15)
    start = numpy.array([-0.5 * length * math.cos(heading), -0.5 * length * math.sin(heading)])
    main = {"start": start, "heading": heading, "length": length, "radius": radius, "bends": rng.normal(0.0, 0.12, 8)}
    axes = [main]
    for _ in range(int(rng.integers(0, p["branches"] + 1))):
        fraction = rng.uniform(0.25, 0.8)
        side = rng.choice([-1.0, 1.0]) * math.radians(rng.uniform(25.0, 55.0))
        origin = start + fraction * length * numpy.array([math.cos(heading), math.sin(heading)])
        axes.append({"start": origin, "heading": heading + side, "length": length * rng.uniform(0.2, 0.5), "radius": radius * 0.55, "bends": rng.normal(0.0, 0.18, 8)})
    return axes


def axis_nodes(axis, nodes):
    points = [axis["start"]]
    heading = axis["heading"]
    step = axis["length"] / (nodes - 1)
    for index in range(nodes - 1):
        heading += axis["bends"][index % len(axis["bends"])]
        points.append(points[-1] + step * numpy.array([math.cos(heading), math.sin(heading)]))
    return points


def add_tube(mesh, points, radius, sides, phase):
    rings = []
    count = len(points)
    for index, point in enumerate(points):
        ahead = points[min(index + 1, count - 1)] - points[max(index - 1, 0)]
        tangent = unit(numpy.array([ahead[0], ahead[1], 0.0]))
        across = numpy.array([-tangent[1], tangent[0], 0.0])
        local = radius * (1.0 - 0.4 * index / (count - 1))
        centre = numpy.array([point[0], point[1], local])
        ring = []
        for side in range(sides):
            angle = 2.0 * math.pi * side / sides
            offset = across * math.cos(angle) * local + numpy.array([0.0, 0.0, local * math.sin(angle)])
            ring.append(mesh.vertex(centre + offset, (0.0, phase, 0.0, 0.0), phase))
        rings.append((ring, centre))
    for index in range(count - 1):
        lower, upper = rings[index][0], rings[index + 1][0]
        for side in range(sides):
            following = (side + 1) % sides
            us = (side / sides, (side + 1) / sides)
            vs = (index / (count - 1), (index + 1) / (count - 1))
            mesh.face((lower[side], lower[following], upper[following], upper[side]), ((us[0], vs[0]), (us[1], vs[0]), (us[1], vs[1]), (us[0], vs[1])))
    for (ring, centre), forward in ((rings[0], False), (rings[-1], True)):
        middle = mesh.vertex(centre, (0.0, phase, 0.0, 0.0), phase)
        for side in range(sides):
            following = (side + 1) % sides
            corners = (ring[side], ring[following], middle) if forward else (ring[following], ring[side], middle)
            mesh.face(corners, ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0)))


def twig_geometry(p, rng, budget):
    axes = twig_axes(p, rng)
    for sides, nodes in TWIG_SHAPES:
        if len(axes) * (2 * sides * (nodes - 1) + 2 * sides) <= budget:
            break
    else:
        sides, nodes = 3, 2
        axes = axes[:max(1, budget // 12)]
    mesh = ElementMesh()
    phase = rng.uniform()
    for axis in axes:
        add_tube(mesh, axis_nodes(axis, nodes), axis["radius"], sides, phase)
    settle(mesh)
    return mesh, {"axes": len(axes), "sides": sides, "nodes": nodes}


def flat_card(mesh, centre, along, across, length, width, phase, lift=CARD_LIFT):
    centre = numpy.array([centre[0], centre[1], lift])
    along = numpy.array([along[0], along[1], 0.0])
    across = numpy.array([across[0], across[1], 0.0])
    corners = [centre - 0.5 * length * along - 0.5 * width * across, centre - 0.5 * length * along + 0.5 * width * across, centre + 0.5 * length * along + 0.5 * width * across, centre + 0.5 * length * along - 0.5 * width * across]
    wind = (0.0, phase, 0.0, 0.0)
    indices = [mesh.vertex(corner, wind, phase) for corner in corners]
    mesh.face(indices, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), smooth=False)


def twig_cards(p, rng, budget):
    axes = twig_axes(p, rng)[: max(1, budget // 2)]
    mesh = ElementMesh()
    phase = rng.uniform()
    for axis in axes:
        nodes = axis_nodes(axis, 3)
        direction = nodes[-1] - nodes[0]
        length = float(numpy.linalg.norm(direction))
        along = direction / length
        flat_card(mesh, 0.5 * (nodes[0] + nodes[-1]), along, (-along[1], along[0]), length * 1.04, 4.0 * axis["radius"], phase)
    return mesh, {"axes": len(axes)}


def leaf_half_width(fraction, width):
    return 0.5 * width * math.sin(math.pi * fraction**0.75)


def leaf_geometry(p, rng, budget):
    for columns, rows in LEAF_GRIDS:
        if 2 * (columns - 1) * (rows - 2) + 2 * (columns - 1) <= budget:
            break
    length = rng.uniform(p["length"][0], p["length"][1])
    width = p["aspect"] * length
    curl = p["curl"] * rng.uniform(0.4, 1.2)
    arch = p["arch"] * rng.uniform(-0.5, 1.0)
    phase = rng.uniform()
    mesh = ElementMesh()
    grid = []
    for row in range(rows + 1):
        fraction = row / rows
        y = (fraction - 0.5) * length
        half = leaf_half_width(fraction, width)
        lift = arch * 0.12 * length * math.sin(math.pi * fraction)
        if row in (0, rows):
            grid.append([mesh.vertex((0.0, y, lift), (0.0, phase, 0.0, 0.0), phase)] * columns)
            continue
        line = []
        for column in range(columns):
            share = 2.0 * column / (columns - 1) - 1.0
            z = lift + curl * 0.35 * half * share * share
            line.append(mesh.vertex((share * half, y, z), (abs(share), phase, 0.0, 0.0), phase))
        grid.append(line)
    for row in range(rows):
        v0, v1 = row / rows, (row + 1) / rows
        for column in range(columns - 1):
            s0 = 2.0 * column / (columns - 1) - 1.0
            s1 = 2.0 * (column + 1) / (columns - 1) - 1.0
            u = [0.5 + 0.4 * s * leaf_half_width(v, 1.0) / 0.5 for s, v in ((s0, v0), (s1, v0), (s1, v1), (s0, v1))]
            a, b, c, d = grid[row][column], grid[row][column + 1], grid[row + 1][column + 1], grid[row + 1][column]
            if row == 0:
                mesh.face((a, c, d), ((0.5, v0), (u[2], v1), (u[3], v1)))
            elif row == rows - 1:
                mesh.face((a, b, c), ((u[0], v0), (u[1], v0), (0.5, v1)))
            else:
                mesh.face((a, b, c, d), ((u[0], v0), (u[1], v0), (u[2], v1), (u[3], v1)))
    settle(mesh)
    return mesh, {"rows": rows, "columns": columns, "length": round(length, 6)}


def leaf_cards(p, rng, budget):
    length = rng.uniform(p["length"][0], p["length"][1])
    mesh = ElementMesh()
    flat_card(mesh, (0.0, 0.0), (0.0, 1.0), (1.0, 0.0), length, length, rng.uniform())
    return mesh, {"length": round(length, 6)}


def settle(mesh):
    lowest = min(point[2] for point in mesh.points)
    mesh.points = [(x, y, z - lowest) for x, y, z in mesh.points]


def pebble_geometry(p, rng, budget):
    level = next((level for level in PEBBLE_LEVELS if 20 * 4 ** (level - 1) <= budget), 1)
    radius = rng.uniform(p["size"][0], p["size"][1])
    stretch = numpy.array([rng.uniform(1.0, 1.0 + p["elongation"]), 1.0, rng.uniform(1.0 - p["flatness"], 1.0 - 0.5 * p["flatness"])])
    waves = [(unit(rng.normal(size=3)), rng.uniform(2.0, 5.0), rng.uniform(0.0, 2.0 * math.pi), rng.uniform(0.3, 1.0)) for _ in range(4)]
    scratch = bmesh.new()
    bmesh.ops.create_icosphere(scratch, subdivisions=level, radius=1.0)
    mesh = ElementMesh()
    phase = rng.uniform()
    index_of = {}
    for vertex in scratch.verts:
        direction = numpy.array(vertex.co)
        bump = sum(weight * math.sin(frequency * float(numpy.dot(axis, direction)) + offset) for axis, frequency, offset, weight in waves) / 2.8
        position = direction * stretch * radius * (1.0 + p["roughness"] * 0.18 * bump)
        index_of[vertex.index] = mesh.vertex(position, (0.0, phase, 0.0, 0.0), phase)
    for face in scratch.faces:
        corners = [index_of[vertex.index] for vertex in face.verts]
        uvs = [(0.5 + 0.5 * vertex.co.x, 0.5 + 0.5 * vertex.co.y) for vertex in face.verts]
        mesh.face(corners, uvs)
    scratch.free()
    settle(mesh)
    return mesh, {"subdivisions": level, "radius": round(radius, 6)}


def pebble_cards(p, rng, budget):
    radius = rng.uniform(p["size"][0], p["size"][1])
    mesh = ElementMesh()
    angle = rng.uniform(0.0, math.pi)
    along = (math.cos(angle), math.sin(angle))
    flat_card(mesh, (0.0, 0.0), along, (-along[1], along[0]), 2.0 * radius * (1.0 + 0.5 * p["elongation"]), 2.0 * radius, rng.uniform())
    return mesh, {"radius": round(radius, 6)}
