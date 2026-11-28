"""Ferns and tall herbs built in code.

Understorey plants built in code: ferns as a shuttlecock of arching fronds with paired pinnae, and tall herbs of the
woodland fringe, an umbellifer (cow parsley) with compound umbels of white flowers and a nettle with opposite leaves.
Every leaf is a UV square of a leaf material whose outline is cut out with alpha, so a plant costs hundreds of
triangles and is drawn as instances."""
import math

import bpy
import numpy

from .commands.procedural import material_procedural
from .registry import COMMANDS
from .schema import validate

LEAF, STEM, FLOWER = 0, 1, 2
FERN_COLOURS = {"color": [0.05, 0.14, 0.03], "dark_color": [0.02, 0.06, 0.012], "underside_color": [0.08, 0.15, 0.05]}
HERB_COLOURS = {"color": [0.045, 0.12, 0.025], "dark_color": [0.015, 0.05, 0.01], "underside_color": [0.08, 0.14, 0.05]}
STEM_COLOUR = (0.06, 0.1, 0.03, 1.0)
FLOWER_COLOUR = (0.75, 0.75, 0.68, 1.0)


class Builder:
    def __init__(self):
        self.vertices, self.faces, self.uvs, self.materials = [], [], [], []

    def quad(self, corners, uvs, material):
        start = len(self.vertices)
        self.vertices.extend(corners)
        self.faces.append((start, start + 1, start + 2, start + 3))
        self.uvs.append(uvs)
        self.materials.append(material)

    def leaf(self, base, along, side, length, width, material=LEAF):
        """A leaf card from base along a unit direction, side its unit width direction; UV v runs to the tip."""
        half = 0.5 * width * side
        tip = base + along * length
        self.quad([base - half, base + half, tip + half, tip - half], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], material)

    def tube(self, points, radius, material=STEM):
        """A three-sided tube through the points, tapering to a third of radius."""
        for index in range(len(points) - 1):
            a, b = points[index], points[index + 1]
            axis = b - a
            axis = axis / max(numpy.linalg.norm(axis), 1e-9)
            helper = numpy.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else numpy.array([0.0, 1.0, 0.0])
            u = numpy.cross(axis, helper)
            u /= numpy.linalg.norm(u)
            v = numpy.cross(axis, u)
            ra = radius * (1.0 - 0.66 * index / max(len(points) - 1, 1))
            rb = radius * (1.0 - 0.66 * (index + 1) / max(len(points) - 1, 1))
            for side in range(3):
                t0, t1 = 2.0 * math.pi * side / 3.0, 2.0 * math.pi * (side + 1) / 3.0
                d0, d1 = u * math.cos(t0) + v * math.sin(t0), u * math.cos(t1) + v * math.sin(t1)
                self.quad([a + d0 * ra, a + d1 * ra, b + d1 * rb, b + d0 * rb], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], material)

    def mesh(self, name):
        data = bpy.data.meshes.new(name)
        data.from_pydata([tuple(point) for point in self.vertices], [], self.faces)
        layer = data.uv_layers.new(name="UVMap")
        flat = [uv for quad in self.uvs for uv in quad]
        layer.data.foreach_set("uv", numpy.array(flat, dtype=numpy.float32).ravel())
        data.polygons.foreach_set("material_index", numpy.array(self.materials, dtype=numpy.int32))
        data.update()
        return data


def arch(rng, length, rise, lean, heading, droop, steps):
    """Points of an arching axis: leaving at lean degrees from vertical towards heading and bending down by droop."""
    direction = numpy.array([math.sin(math.radians(lean)) * math.cos(heading), math.sin(math.radians(lean)) * math.sin(heading), math.cos(math.radians(lean))])
    points = [numpy.array([0.0, 0.0, rise])]
    for step in range(steps):
        share = (step + 1) / steps
        bend = numpy.array([0.0, 0.0, -droop * share * 2.2 / steps])
        direction = direction + bend
        direction /= numpy.linalg.norm(direction)
        points.append(points[-1] + direction * length / steps)
    return points


def frond(builder, rng, points, pinna_length, pairs, width):
    builder.tube(points, 0.004)
    total = len(points) - 1
    for pair in range(pairs):
        share = (pair + 1.0) / (pairs + 1.0)
        position = share * total
        index = min(int(position), total - 1)
        part = position - index
        base = points[index] * (1.0 - part) + points[index + 1] * part
        along = points[index + 1] - points[index]
        along /= numpy.linalg.norm(along)
        side = numpy.cross(along, numpy.array([0.0, 0.0, 1.0]))
        if numpy.linalg.norm(side) < 1e-6:
            side = numpy.array([1.0, 0.0, 0.0])
        side /= numpy.linalg.norm(side)
        normal = numpy.cross(side, along)
        length = pinna_length * math.sin(math.pi * min(0.15 + share, 1.0)) ** 0.7 * (1.0 - 0.35 * share) * (0.9 + 0.2 * rng.random())
        for sign in (-1.0, 1.0):
            out = sign * side * math.cos(math.radians(25.0)) + along * math.sin(math.radians(25.0)) - normal * 0.25
            out /= numpy.linalg.norm(out)
            width_dir = numpy.cross(normal, out)
            width_dir /= numpy.linalg.norm(width_dir)
            builder.leaf(base, out, width_dir, length, width * length)


def fern(rng, size):
    builder = Builder()
    fronds = int(rng.integers(9, 15))
    for index in range(fronds):
        heading = 2.0 * math.pi * (index + 0.4 * rng.random()) / fronds
        length = size * (0.75 + 0.45 * rng.random())
        points = arch(rng, length, 0.02, 25.0 + 30.0 * rng.random(), heading, 0.7 + 0.6 * rng.random(), 10)
        frond(builder, rng, points, 0.2 * size, int(rng.integers(20, 29)), 0.4)
    return builder


def umbel(builder, rng, top, size):
    rays = int(rng.integers(10, 15))
    for ray in range(rays):
        heading = 2.0 * math.pi * ray / rays + 0.25 * rng.random()
        spread = math.radians(20.0 + 45.0 * rng.random())
        reach = 0.09 * size * (0.8 + 0.4 * rng.random())
        end = top + reach * numpy.array([math.sin(spread) * math.cos(heading), math.sin(spread) * math.sin(heading), math.cos(spread)])
        builder.tube([top, end], 0.0012)
        radius = 0.013 * size
        for floret in range(6):
            turn = heading + 2.0 * math.pi * floret / 6.0
            side = numpy.array([-math.sin(turn), math.cos(turn), 0.0])
            flat = numpy.array([math.cos(turn), math.sin(turn), 0.0])
            centre = end + 0.6 * radius * flat + numpy.array([0.0, 0.0, 0.003 * floret])
            builder.quad([centre - side * radius - flat * radius, centre + side * radius - flat * radius, centre + side * radius + flat * radius, centre - side * radius + flat * radius],
                         [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], FLOWER)


def umbellifer(rng, size):
    builder = Builder()
    height = size * (0.85 + 0.3 * rng.random())
    lean = rng.normal(0.0, 0.05, 2)
    stem = [numpy.array([lean[0] * height * share ** 2, lean[1] * height * share ** 2, height * share]) for share in numpy.linspace(0.0, 1.0, 7)]
    builder.tube(stem, 0.007)
    umbel(builder, rng, stem[-1], size)
    for branch in range(int(rng.integers(2, 5))):
        share = 0.45 + 0.35 * rng.random()
        base = stem[0] * (1.0 - share) + stem[-1] * share
        heading = 2.0 * math.pi * rng.random()
        rise = 0.25 * size * (1.0 - share) + 0.12 * size
        top = base + numpy.array([0.4 * rise * math.cos(heading), 0.4 * rise * math.sin(heading), rise])
        builder.tube([base, 0.5 * (base + top) + numpy.array([0.0, 0.0, 0.02]), top], 0.004)
        umbel(builder, rng, top, 0.8 * size)
    for leaf in range(int(rng.integers(4, 7))):
        heading = 2.0 * math.pi * rng.random()
        points = arch(rng, 0.4 * size * (0.8 + 0.4 * rng.random()), 0.0, 45.0 + 25.0 * rng.random(), heading, 0.8, 6)
        frond(builder, rng, points, 0.12 * size, 9, 0.6)
    return builder


def nettle(rng, size):
    builder = Builder()
    for shoot in range(int(rng.integers(3, 6))):
        height = size * (0.7 + 0.4 * rng.random())
        offset = rng.normal(0.0, 0.06, 2)
        lean = rng.normal(0.0, 0.06, 2)
        stem = [numpy.array([offset[0] + lean[0] * height * share, offset[1] + lean[1] * height * share, height * share]) for share in numpy.linspace(0.0, 1.0, 7)]
        builder.tube(stem, 0.004)
        nodes = int(rng.integers(7, 11))
        for node in range(nodes):
            share = (node + 1.0) / (nodes + 0.5)
            base = stem[0] * (1.0 - share) + stem[-1] * share
            heading = node * math.pi / 2.0 + 0.3 * rng.random()
            length = 0.2 * size * (1.0 - 0.5 * share) + 0.04
            for sign in (-1.0, 1.0):
                out = numpy.array([sign * math.cos(heading), sign * math.sin(heading), 0.45 - 0.7 * share])
                out /= numpy.linalg.norm(out)
                width_dir = numpy.cross(numpy.array([0.0, 0.0, 1.0]), out)
                width_dir /= max(numpy.linalg.norm(width_dir), 1e-9)
                builder.leaf(base, out, width_dir, length, 0.65 * length)
    return builder


FORMS = {"fern": (fern,), "herb": (umbellifer, nettle)}


def plant_materials(ctx, prefix):
    names = {"fern": f"{prefix}_fern_leaf", "herb": f"{prefix}_herb_leaf"}
    for kind, colours, shape in (("fern", FERN_COLOURS, "lanceolate"), ("herb", HERB_COLOURS, "ovate")):
        if bpy.data.materials.get(names[kind]) is None:
            params = {**colours, "cutout": True, "shape": shape, "vein_pairs": 6, "translucency": 0.45}
            material_procedural(ctx, validate(COMMANDS["material_procedural"].schema, {"name": names[kind], "leaf": params}))
    plain = {}
    for key, colour in (("stem", STEM_COLOUR), ("flower", FLOWER_COLOUR)):
        name = f"{prefix}_{key}"
        material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        material.use_nodes = True
        shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value = colour
        shader.inputs["Roughness"].default_value = 0.6
        material.diffuse_color = colour
        plain[key] = material
    return {kind: [bpy.data.materials[names[kind]], plain["stem"], plain["flower"]] for kind in names}


def build_plants(ctx, prefix, kind, count, seed, size):
    """count meshes of kind (fern or herb), each its own seeded plant of about size metres, alternating the forms."""
    materials = plant_materials(ctx, prefix)[kind]
    meshes = []
    for index in range(count):
        rng = numpy.random.default_rng([seed, index, len(kind)])
        form = FORMS[kind][index % len(FORMS[kind])]
        data = form(rng, size).mesh(f"{prefix}_{kind}_{index:03d}")
        for material in materials:
            data.materials.append(material)
        meshes.append(data)
    return meshes
