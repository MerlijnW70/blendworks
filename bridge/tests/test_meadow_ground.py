"""Tests of the meadow ground material: no tiling, mid-distance colour, distant land."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import bpy
import numpy

from land_helpers import region
from meadow_helpers import fields_of, uv_grid_mesh
from natural_stats import baked_pixels, luminance_of

PIXELS = 128
SMALLEST_LAG = 16
TILING_LIMIT = 0.35
TILED_LEAST = 0.8
DISTANCES = (3.0, 30.0, 300.0)


def blurred(values, sigma):
    reach = int(3 * sigma)
    offsets = numpy.arange(-reach, reach + 1)
    kernel = numpy.exp(-0.5 * (offsets / sigma) ** 2)
    kernel /= kernel.sum()
    padded = numpy.pad(values, reach, mode="reflect")
    rows = numpy.array([numpy.convolve(row, kernel, mode="valid") for row in padded])
    return numpy.array([numpy.convolve(column, kernel, mode="valid") for column in rows.T]).T


def tiling_measure(image):
    """The largest autocorrelation of the image's detail (the image less its blur over SMALLEST_LAG / 4 pixels) at any shift
    of SMALLEST_LAG pixels or more, up to half the image: about 1 where a texture repeats, near 0 where it never does."""
    size = image.shape[0]
    detail = image - blurred(image, SMALLEST_LAG / 4.0)
    detail = detail - detail.mean()
    padded = numpy.zeros((2 * size, 2 * size))
    padded[:size, :size] = detail
    ones = numpy.zeros((2 * size, 2 * size))
    ones[:size, :size] = 1.0
    spectrum = numpy.fft.fft2(padded)
    product = numpy.real(numpy.fft.ifft2(spectrum * numpy.conj(spectrum)))
    overlap = numpy.real(numpy.fft.ifft2(numpy.abs(numpy.fft.fft2(ones)) ** 2))
    lags = numpy.fft.fftfreq(2 * size, 1.0 / (2 * size))
    dy, dx = numpy.meshgrid(lags, lags, indexing="ij")
    reach = numpy.hypot(dx, dy)
    keep = (reach >= SMALLEST_LAG) & (numpy.abs(dx) <= size / 2) & (numpy.abs(dy) <= size / 2)
    correlation = product / numpy.maximum(overlap, 1.0) / max(detail.var(), 1e-12)
    return float(correlation[keep].max())


def bake_luminance(bridge, name):
    bridge.ok("bake", names=[name], channels=["base_color"], size=PIXELS, device="cpu", overwrite=True, samples={"base_color": 1}, time_limit=600.0)
    return luminance_of(baked_pixels(f"{name}_base_color", PIXELS))


def meadow_plane(bridge, name, size):
    uv_grid_mesh(bridge, name, size, 11, lambda x, y: 0.0 * x)
    bridge.ok("material_procedural", name=f"{name}_ground", grass_ground={"density": 0.75, "dryness": 0.2})
    bridge.ok("assign_material", name=name, material=f"{name}_ground")
    bridge.ok("meadow_fields", targets=[name], seed=2)


def tiled_material(name, period):
    """A control: noise on a coordinate that wraps every period metres, so it repeats."""
    from blendworks_bridge.nodes import Graph

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    graph = Graph(material.node_tree)
    shader = material.node_tree.nodes["Principled BSDF"]
    position = graph.node("ShaderNodeNewGeometry").outputs["Position"]
    wrapped = graph.vector_math("FRACTION", graph.vector_math("MULTIPLY", position, (1.0 / period, 1.0 / period, 1.0)))
    graph.set(shader.inputs["Base Color"], graph.noise(wrapped, 6.0, detail=4.0).outputs["Color"])
    return material


def test_the_ground_does_not_repeat_at_three_distances(bridge):
    for index, size in enumerate(DISTANCES):
        name = f"Meadow{index}"
        meadow_plane(bridge, name, size)
        assert bpy.data.materials[f"{name}_ground"].node_tree.nodes.get("meadow_ground_mix") is not None
        measure = tiling_measure(bake_luminance(bridge, name))
        assert measure < TILING_LIMIT, (size, measure)
        mix = bpy.data.materials[f"{name}_ground"].node_tree.nodes["meadow_ground_mix"]
        mix.inputs[0].default_value = 0.0
        alone = tiling_measure(bake_luminance(bridge, name))
        assert alone < TILING_LIMIT, (size, "meadow layer alone", alone)
        control = f"Tiled{index}"
        bridge.ok("add_primitive", type="plane", name=control, size=size, location=[3.0 * size, 0.0, 0.0])
        bpy.data.objects[control].data.materials.append(tiled_material(f"{control}_tiled", size / 4.0))
        assert tiling_measure(bake_luminance(bridge, control)) > TILED_LEAST, size


def test_the_ground_carries_the_meadow_colour_at_mid_distance(bridge):
    count = 61
    uv_grid_mesh(bridge, "Ground", 300.0, count, lambda x, y: 0.0015 * (x * x + y * y) - 4.0 + 1.5 * numpy.sin(x / 37.0))
    bridge.ok("liquid_body", kind="lake", name="Lake", ground=["Ground"], point=[0.0, 0.0, 0.0], level=-2.5, seed=1)
    bridge.ok("material_procedural", name="ground", grass_ground={"density": 0.75, "dryness": 0.2})
    bridge.ok("assign_material", name="Ground", material="ground")
    plain = bake_luminance(bridge, "Ground")
    bridge.ok("meadow_fields", targets=["Ground"], seed=2)
    structured = bake_luminance(bridge, "Ground")
    moisture = fields_of("Ground")["moisture"].reshape(count, count)
    pixel = (numpy.arange(PIXELS) + 0.5) / PIXELS * (count - 1)
    nearest = numpy.clip(numpy.round(pixel).astype(int), 0, count - 1)
    at_pixels = moisture[nearest[:, None], nearest[None, :]]
    dry = at_pixels < 0.99
    coarse = lambda values: blurred(values, 4.0)
    spread = lambda values: float(coarse(values)[dry].std() / coarse(values)[dry].mean())
    correlation = float(numpy.corrcoef(coarse(structured)[dry], at_pixels[dry])[0, 1])
    assert spread(structured) > 2.0 * spread(plain), (spread(structured), spread(plain))
    assert correlation < -0.3, correlation


def test_distant_land_continues_the_fields_and_their_colour(bridge):
    region(bridge)
    bridge.ok("material_procedural", name="ground", grass_ground={})
    bridge.ok("assign_material", name="land", material="ground")
    bridge.ok("meadow_fields", targets=["land"], seed=1)
    made = bridge.ok("distant_land", name="Far", terrain=["land"], detail=16, behind=1.0)
    bridge.ok("meadow_fields", targets=["Far"], seed=1, paths="none")
    assert bpy.data.materials[made["material"]].node_tree.nodes.get("meadow_ground_mix") is not None
    far = fields_of("Far")
    assert far["moisture"].std() > 0.03 and far["grazing"].std() > 0.03


run(globals())
