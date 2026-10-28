import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy

from harness import run

SIZE = 1024
INNER, OUTER, SPAN = 0.05, 0.14, 0.3
SEGMENTS = 96
SAMPLE_ANGLES = [index * 30.0 for index in range(12)]
SAMPLE_RADIUS = 0.095
WINDOW = 0.06
SCRATCH_SCALE = 0.2
MAX_TANGENT_ERROR = 12.0
MIN_COHERENCE = 0.5
MIN_SIGNAL = 0.002


def annulus(bridge, plane="xy"):
    vertices, uvs, faces = [], [], []
    for index in range(SEGMENTS):
        angle = 2 * math.pi * index / SEGMENTS
        for radius in (INNER, OUTER):
            x, y = radius * math.cos(angle), radius * math.sin(angle)
            vertices.append([x, y, 0.0] if plane == "xy" else [x, 0.0, y])
            uvs.append([(x + SPAN / 2) / SPAN, (y + SPAN / 2) / SPAN])
    for index in range(SEGMENTS):
        following = (index + 1) % SEGMENTS
        faces.append([2 * index, 2 * index + 1, 2 * following + 1, 2 * following])
    bridge.ok("mesh_from_data", name="Ring", vertices=vertices, vertex_uvs=uvs, faces=faces)


def roughness_of_ring(bridge, **brass):
    bridge.ok("material_procedural", name="Turned", brass={"polish": 0.2, "patina": 0.0, "scratch_scale": SCRATCH_SCALE, **brass})
    bridge.ok("assign_material", name="Ring", material="Turned")
    bridge.ok("bake", names=["Ring"], channels=["roughness"], size=SIZE, overwrite=True, samples={"roughness": 1}, prefix="Ring", device="cpu", margin=0, float_buffer=True, time_limit=600.0)
    pixels = numpy.array(bpy.data.images["Ring_roughness"].pixels[:], dtype=numpy.float64).reshape(SIZE, SIZE, 4)
    return pixels[..., 0]


def line_direction(patch):
    gradient_y, gradient_x = numpy.gradient(patch)
    xx, yy, xy = (gradient_x ** 2).sum(), (gradient_y ** 2).sum(), (gradient_x * gradient_y).sum()
    total = xx + yy
    if total <= 0.0 or patch.std() < MIN_SIGNAL:
        return None, 0.0
    coherence = math.sqrt((xx - yy) ** 2 + 4 * xy ** 2) / total
    gradient_angle = 0.5 * math.atan2(2 * xy, xx - yy)
    return math.degrees(gradient_angle) + 90.0, coherence


def tangent_errors(image):
    half = int(WINDOW / SPAN * SIZE / 2)
    errors = []
    for degrees in SAMPLE_ANGLES:
        angle = math.radians(degrees)
        column = int((SAMPLE_RADIUS * math.cos(angle) + SPAN / 2) / SPAN * SIZE)
        row = int((SAMPLE_RADIUS * math.sin(angle) + SPAN / 2) / SPAN * SIZE)
        direction, coherence = line_direction(image[row - half : row + half, column - half : column + half])
        if direction is None:
            errors.append(None)
            continue
        difference = abs(direction - (degrees + 90.0)) % 180.0
        errors.append((min(difference, 180.0 - difference), coherence))
    return errors


def assert_follows_the_ring(errors, what):
    assert all(entry is not None for entry in errors), (what, "no scratches at some sample points", errors)
    worst = max(error for error, _ in errors)
    assert worst <= MAX_TANGENT_ERROR, (what, "scratches leave the tangent by", worst)
    assert min(coherence for _, coherence in errors) >= MIN_COHERENCE, (what, errors)


def test_the_default_direction_is_circumferential_and_documented(bridge):
    from blendworks_bridge.presets import PRESETS

    properties = PRESETS["brass"].properties
    assert properties["scratch_direction"]["default"] == "around_z"
    assert "ring" in properties["scratch_direction"]["description"] and "flat stock" in properties["scratch_direction"]["description"]
    assert {"around", "u", "v"} <= set(properties["scratch_direction"]["enum"]) and properties["scratch_axis"]["default"] == [0.0, 0.0, 1.0]
    annulus(bridge)
    assert_follows_the_ring(tangent_errors(roughness_of_ring(bridge)), "default")


def test_scratches_around_a_ring_follow_its_tangent_and_straight_ones_do_not(bridge):
    annulus(bridge)
    assert_follows_the_ring(tangent_errors(roughness_of_ring(bridge, scratch_direction="around_z")), "around_z")
    for straight in ("x", "y"):
        try:
            assert_follows_the_ring(tangent_errors(roughness_of_ring(bridge, scratch_direction=straight)), straight)
        except AssertionError:
            continue
        raise AssertionError(f"straight scratches along {straight} must fail the circumferential test")


def test_a_free_axis_turns_the_scratches_about_that_axis(bridge):
    annulus(bridge, plane="xz")
    assert_follows_the_ring(tangent_errors(roughness_of_ring(bridge, scratch_direction="around", scratch_axis=[0.0, 3.0, 0.0])), "around y")
    try:
        assert_follows_the_ring(tangent_errors(roughness_of_ring(bridge, scratch_direction="around_z")), "around z on a ring about y")
    except AssertionError:
        pass
    else:
        raise AssertionError("scratches around the wrong axis must not follow the ring")
    bridge.refuse("material_procedural", "bad_args", name="Zero", brass={"scratch_direction": "around", "scratch_axis": [0.0, 0.0, 0.0]})


def test_uv_directions_follow_the_unwrapped_surface(bridge):
    annulus(bridge)
    column = SIZE // 2
    row = int((SAMPLE_RADIUS + SPAN / 2) / SPAN * SIZE)
    half = int(WINDOW / SPAN * SIZE / 2)
    for direction, expected in (("u", 0.0), ("v", 90.0)):
        image = roughness_of_ring(bridge, scratch_direction=direction, coordinates="object")
        line, coherence = line_direction(image[row - half : row + half, column - half : column + half])
        assert line is not None and coherence >= MIN_COHERENCE, (direction, coherence)
        assert min(abs(line - expected) % 180.0, 180.0 - abs(line - expected) % 180.0) <= MAX_TANGENT_ERROR, (direction, line)


run(globals())
