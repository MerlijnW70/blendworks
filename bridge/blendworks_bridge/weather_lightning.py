import math
import random

import bpy
from mathutils import Vector

from . import weather_objects

LEVELS = 7
ROUGHNESS = 0.22
BRANCHES = 5
CHANNEL_RADIUS = 2.5
BOLT_STRENGTH = 60.0
FLASH_POWER = 2.0e7


def zigzag(generator, start, end, levels, roughness):
    points = [start, end]
    for level in range(levels):
        refined = [points[0]]
        for a, b in zip(points, points[1:]):
            segment = b - a
            length = segment.length
            side = Vector((generator.gauss(0.0, 1.0), generator.gauss(0.0, 1.0), generator.gauss(0.0, 0.25)))
            side -= segment.normalized() * side.dot(segment.normalized())
            middle = (a + b) / 2.0 + side * (roughness * length * 0.5)
            refined.extend([middle, b])
        points = refined
    return points


def bolt_paths(seed, top, ground):
    generator = random.Random(seed)
    main = zigzag(generator, top, ground, LEVELS, ROUGHNESS)
    paths = [(main, 1.0)]
    for _ in range(BRANCHES):
        index = generator.randrange(2, len(main) // 2)
        start = main[index]
        drop = (start.z - ground.z) * generator.uniform(0.15, 0.4)
        heading = generator.uniform(0.0, 2.0 * math.pi)
        end = start + Vector((math.cos(heading) * drop * 0.6, math.sin(heading) * drop * 0.6, -drop))
        paths.append((zigzag(generator, start, end, LEVELS - 2, ROUGHNESS * 1.2), 0.45))
    return paths


def bolt_material():
    material = bpy.data.materials.new("Lightning")
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.78, 0.84, 1.0, 1.0)
    emission.inputs["Strength"].default_value = BOLT_STRENGTH
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return material


def add(scene, seed, top, ground, flash, sky_scale):
    """A branching bolt from the cloud base to the ground, glowing, and a flash light under the base."""
    curve = bpy.data.curves.new("Lightning", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = CHANNEL_RADIUS
    curve.bevel_resolution = 1
    for points, width in bolt_paths(seed, Vector(top), Vector(ground)):
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for index, point in enumerate(points):
            spline.points[index].co = (point.x, point.y, point.z, 1.0)
            spline.points[index].radius = width * (1.0 - 0.5 * index / len(points))
    curve.materials.append(bolt_material())
    bolt = bpy.data.objects.new("Lightning", curve)
    weather_objects.link(scene, bolt, "lightning")
    for name in ("visible_diffuse", "visible_glossy", "visible_shadow", "visible_transmission"):
        setattr(bolt, name, False)
    light = None
    if flash > 0.0:
        data = bpy.data.lights.new("Lightning flash", "POINT")
        data.energy = FLASH_POWER * flash * sky_scale * 32.0
        data.color = (0.8, 0.86, 1.0)
        data.shadow_soft_size = 200.0
        light = bpy.data.objects.new("Lightning flash", data)
        weather_objects.link(scene, light, "flash")
        light.location = (top[0], top[1], top[2] + 400.0)
    return bolt, light
