"""Sunlit grass is bright: two-sided leaves with cited optics, erectophile blades, canopy reflectance in the cited range,
near and far grass alike, and water that reflects by Fresnel."""
import colorsys
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT
from harness import close, run

from blendworks_bridge import cover_blades, cover_ground, cover_kinds, cover_presets, exr_read, leaf_optics, meadow_rules, natural, sky_world
from blendworks_bridge.nodes import Graph

QUICK = dict(EXACT, width=160, height=120, samples=24)
LUMINANCE = np.array([0.2126, 0.7152, 0.0722])
LEAF_TOLERANCE = 0.12
GREEN_TRANSMITTANCE = (0.05, 0.15)
ERECTOPHILE_TOLERANCE = 5.0
SHAPE_TOLERANCE = 0.15
FRONT_LIT_SHARE = 0.75
BACKLIT_SHARE = 0.6
NEAR_FAR_RATIO = (0.75, 1.33)
NEAR_FAR_HUE = 15.0
WATER_IOR = 1.333
WATER_TOLERANCE = 0.05
LAWN = [{"name": "lawn", "element": "grass", "density": 400.0, "params": {"blades": 16, "height": [0.1, 0.3], "dry_tips": 0.0}}]


def exr(bridge, name):
    return exr_read.read_exr(os.path.join(bridge.workspace, f"{name}.exr")).stack("", "RGB")


def vegetation_materials():
    return [material for material in bpy.data.materials if material.node_tree is not None
            and any(node.name == leaf_optics.TRANSLUCENT_NODE for node in material.node_tree.nodes)]


def test_no_vegetation_material_uses_transmission_weight(bridge):
    bridge.ok("material_procedural", name="Broad", leaf={"cutout": True})
    bridge.ok("material_procedural", name="Needles", leaf={"shape": "brush"})
    bridge.ok("material_procedural", name="Petal", leaf={"leaf_type": "petal", "color": [0.9, 0.7, 0.05]})
    bridge.ok("add_primitive", type="plane", name="Land", size=4.0)
    bridge.ok("add_camera", name="Cam", location=[0.0, -3.0, 1.5], target=[0.0, 0.0, 0.0])
    bridge.ok("ground_cover", target="Land", preset="meadow", camera="Cam", near=6.0, view_only=True, seed=1)
    leaves = [material.name for material in bpy.data.materials if material.name.startswith("GroundCover") and "pebble" not in material.name
              and "twig" not in material.name and "mound" not in material.name and "centre" not in material.name]
    assert leaves, [material.name for material in bpy.data.materials]
    two_sided = {material.name for material in vegetation_materials()}
    for name in leaves + ["Broad", "Needles", "Petal"]:
        material = bpy.data.materials[name]
        for node in material.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                transmission = node.inputs["Transmission Weight"]
                assert not transmission.is_linked and transmission.default_value == 0.0, name
                assert node.inputs["Subsurface Weight"].default_value == 0.0, name
    missing = [name for name in leaves + ["Broad", "Needles", "Petal"] if name not in two_sided and "_2" not in name]
    assert not missing, missing


def matte(material):
    """No specular sheen, so a render measures the diffuse reflectance and transmittance alone."""
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            node.inputs["Specular IOR Level"].default_value = 0.0


def leaf_plane(bridge, below):
    """A flat leaf of the grass's cited reflectance under a sun from above or below, seen from above."""
    reflectance = leaf_optics.OPTICS["grass"]["reflectance"]
    bridge.ok("add_primitive", type="plane", name="Leaf", size=4.0)
    bridge.ok("add_material", name="Blade", base_color=list(reflectance), roughness=1.0)
    material = bpy.data.materials["Blade"]
    matte(material)
    leaf_optics.two_sided(Graph(material.node_tree), "grass")
    bridge.ok("assign_material", name="Leaf", material="Blade")
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    bridge.ok("add_light", type="sun", name="Lamp", energy=1.0, rotation=[180.0 if below else 0.0, 0.0, 0.0])
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 3.0], rotation=[0.0, 0.0, 0.0], lens=80.0)


def test_leaf_reflects_and_transmits_its_cited_values(bridge):
    leaf_plane(bridge, below=False)
    bridge.ok("render_final", path="front.exr", **QUICK)
    bpy.data.objects["Lamp"].rotation_euler = (math.pi, 0.0, 0.0)
    bridge.ok("render_final", path="back.exr", **QUICK)
    optics = leaf_optics.OPTICS["grass"]
    reflected = exr(bridge, "front").reshape(-1, 3).mean(axis=0) * math.pi
    transmitted = exr(bridge, "back").reshape(-1, 3).mean(axis=0) * math.pi
    assert np.all(np.abs(reflected / np.asarray(optics["reflectance"]) - 1.0) < LEAF_TOLERANCE), reflected
    assert np.all(np.abs(transmitted / np.asarray(optics["transmittance"]) - 1.0) < LEAF_TOLERANCE), transmitted
    assert GREEN_TRANSMITTANCE[0] <= transmitted[1] <= GREEN_TRANSMITTANCE[1], transmitted


def de_wit_erectophile(degrees):
    """de Wit (1965) erectophile leaf inclination density, inclination from horizontal, per degree."""
    theta = np.radians(degrees)
    return 2.0 / math.pi * (1.0 - np.cos(2.0 * theta)) * math.pi / 180.0


def blade_angles(params, clumps=40):
    p = cover_kinds.element_params("grass", params)
    rng = np.random.default_rng(1)
    angles, areas = [], []
    for _ in range(clumps):
        mesh, _ = cover_blades.blade_clump(p, rng, 2000)
        points = mesh.coordinates()
        for face in mesh.faces:
            for index in range(1, len(face) - 1):
                normal = np.cross(points[face[index]] - points[face[0]], points[face[index + 1]] - points[face[0]])
                length = float(np.linalg.norm(normal))
                if length > 0.0:
                    angles.append(math.degrees(math.acos(abs(normal[2]) / length)))
                    areas.append(0.5 * length)
    return np.asarray(angles), np.asarray(areas), float(np.sum(areas)) / clumps


def test_blades_are_erectophile_with_a_grassland_leaf_area_index(bridge):
    lai = 0.0
    bins = np.linspace(0.0, 90.0, 10)
    for population in cover_presets.MEADOW:
        if population["element"] != "grass" or population["name"] == "thatch":
            continue
        angles, areas, per_clump = blade_angles(population.get("params", {}))
        mean = float((angles * areas).sum() / areas.sum())
        assert abs(mean - leaf_optics.ERECTOPHILE_MEAN) < ERECTOPHILE_TOLERANCE, (population["name"], mean)
        measured = np.cumsum(np.histogram(angles, bins, weights=areas)[0]) / areas.sum()
        expected = np.cumsum([float(np.trapezoid(de_wit_erectophile(np.linspace(a, b, 20)), np.linspace(a, b, 20))) for a, b in zip(bins, bins[1:])])
        assert float(np.abs(measured - expected).max()) < SHAPE_TOLERANCE, (population["name"], measured, expected)
        lai += per_clump * population["density"]
    assert leaf_optics.GRASS_LAI[0] <= lai <= leaf_optics.GRASS_LAI[1], lai


def lawn_scene(bridge, cover, azimuth, camera):
    bridge.ok("add_primitive", type="plane", name="Land", size=16.0)
    bridge.ok("material_procedural", name="Ground", grass_ground={"density": 0.75, "dryness": 0.0})
    bridge.ok("assign_material", name="Land", material="Ground")
    bridge.ok("add_camera", name="Cam", **camera)
    bridge.ok("sky", sun={"elevation": 60.0, "azimuth": azimuth})
    if cover:
        bridge.ok("ground_cover", target="Land", camera="Cam", near=20.0, view_only=True, seed=5, populations=LAWN)


def region(bridge, name):
    image = exr(bridge, name)
    height, width = image.shape[:2]
    return image[int(height * 0.4):int(height * 0.85), int(width * 0.25):int(width * 0.75)].reshape(-1, 3).mean(axis=0)


def hue(colour):
    return colorsys.rgb_to_hsv(*np.clip(colour, 1e-6, None))[0] * 360.0


OBLIQUE = {"location": [0.0, -6.0, 1.6], "target": [0.0, 0.0, 0.0], "lens": 35.0}
ABOVE = {"location": [0.0, 0.0, 3.0], "rotation": [0.0, 0.0, 0.0], "lens": 50.0}


def render_lawn(bridge, name, cover, azimuth, camera):
    bridge.ok("new_scene")
    lawn_scene(bridge, cover, azimuth, camera)
    bridge.ok("render_final", path=f"{name}.exr", **QUICK)
    return region(bridge, name), sky_world.illuminant(bpy.context.scene)["illuminance"]


def test_canopy_reflectance_is_the_cited_visible_grassland_albedo(bridge):
    """Grassland reflects 0.18-0.26 of the broadband sun (Oke 1987), most of it in the near infrared; in the visible it
    reflects 0.03-0.10, green the highest (MODIS visible-band albedo of grassland in the growing season, Gao et al. 2005).
    A render holds visible light only, so the visible figure is the one it must meet."""
    colour, light = render_lawn(bridge, "above", True, 200.0, ABOVE)
    reflectance = math.pi * colour / light
    visible = float(reflectance @ LUMINANCE)
    assert leaf_optics.VISIBLE_GRASS_ALBEDO[0] <= visible <= leaf_optics.VISIBLE_GRASS_ALBEDO[1], reflectance
    assert reflectance[1] > reflectance[0] and reflectance[1] > reflectance[2], reflectance
    model = np.asarray(leaf_optics.meadow_colour("grass"))
    assert leaf_optics.VISIBLE_GRASS_ALBEDO[0] <= float(model @ LUMINANCE) <= leaf_optics.VISIBLE_GRASS_ALBEDO[1], model
    assert model[1] > model[0] and model[1] > model[2], model


def test_sunlit_grass_is_bright_and_matches_the_far_ground(bridge):
    for colours in ((natural.GRASS_CANOPY, natural.DRY_CANOPY), (cover_ground.LUSH, cover_ground.STRAW)):
        assert list(colours[0]) == leaf_optics.meadow_colour("grass") and list(colours[1]) == leaf_optics.meadow_colour("straw")
    found = {}
    for azimuth, label in ((200.0, "front"), (20.0, "back")):
        found[label] = (render_lawn(bridge, f"grass_{label}", True, azimuth, OBLIQUE)[0], render_lawn(bridge, f"bare_{label}", False, azimuth, OBLIQUE)[0])
    grass, bare = found["front"]
    ratio = float(grass @ LUMINANCE) / float(bare @ LUMINANCE)
    assert ratio >= FRONT_LIT_SHARE, ratio
    assert NEAR_FAR_RATIO[0] <= ratio <= NEAR_FAR_RATIO[1], ratio
    assert abs(hue(grass) - hue(bare)) < NEAR_FAR_HUE, (hue(grass), hue(bare))
    grass, bare = found["back"]
    assert float(grass @ LUMINANCE) >= BACKLIT_SHARE * float(bare @ LUMINANCE), (grass, bare)


def meadow_ground_colour(bridge, moisture):
    """The meadow ground layer alone, baked, on ground whose fields are uniform at this moisture."""
    from meadow_helpers import uv_grid_mesh
    from natural_stats import to_linear
    name = f"Field{int(moisture * 100)}"
    uv_grid_mesh(bridge, name, 300.0, 11, lambda x, y: 0.0 * x)
    bridge.ok("material_procedural", name=f"{name}_ground", grass_ground={"density": 0.75, "dryness": 0.2})
    bridge.ok("assign_material", name=name, material=f"{name}_ground")
    bridge.ok("meadow_fields", targets=[name], seed=2)
    mesh = bpy.data.objects[name].data
    values = {"moisture": moisture, "soil": 0.5, "disturbance": 0.0, "shade": 0.0, "grazing": 0.5}
    for field, value in values.items():
        mesh.attributes["meadow_" + field].data.foreach_set("value", [value] * len(mesh.vertices))
    bpy.data.materials[f"{name}_ground"].node_tree.nodes[cover_ground.MIX_NAME].inputs[0].default_value = 0.0
    bridge.ok("bake", names=[name], channels=["base_color"], size=32, device="cpu", overwrite=True, samples={"base_color": 1}, time_limit=600.0)
    image = bpy.data.images[f"{name}_base_color"]
    pixels = np.array(image.pixels[:], dtype=np.float64).reshape(32, 32, 4)[..., :3].reshape(-1, 3).mean(axis=0)
    return pixels if image.is_float else to_linear(pixels)


def test_far_ground_dries_by_the_near_meadow_rules(bridge):
    """The ground layer turns to straw where the meadow's own blades do: by the dryness responses of its main grass."""
    short = next(population for population in cover_presets.MEADOW if population["name"] == "short_grass")
    for moisture in (0.2, 0.45):
        fields = {name: np.array([value]) for name, value in {"moisture": moisture, "soil": 0.5, "disturbance": 0.0, "shade": 0.0, "grazing": 0.5}.items()}
        dry = float(np.clip(meadow_rules.effect(short, fields, "dryness")[0], 0.0, 1.0))
        expected = (1.0 - dry) * np.asarray(cover_ground.LUSH) + dry * np.asarray(cover_ground.STRAW)
        found = meadow_ground_colour(bridge, moisture)
        assert abs(hue(found) - hue(expected)) < NEAR_FAR_HUE, (moisture, dry, found, expected)


def fresnel(cosine, ior):
    sine = math.sqrt(1.0 - cosine * cosine) / ior
    through = math.sqrt(1.0 - sine * sine)
    perpendicular = (cosine - ior * through) / (cosine + ior * through)
    parallel = (ior * cosine - through) / (ior * cosine + through)
    return 0.5 * (perpendicular ** 2 + parallel ** 2)


def test_water_reflects_by_fresnel_at_grazing_incidence(bridge):
    bridge.ok("add_primitive", type="plane", name="Water", size=400.0)
    bridge.ok("material_liquid", preset="water_fresh", name="Lake", objects=["Water"])
    bridge.ok("add_primitive", type="plane", name="Floor", size=400.0, location=[0.0, 0.0, -0.5])
    bridge.ok("add_material", name="Black", base_color=[0.0, 0.0, 0.0], roughness=1.0)
    matte(bpy.data.materials["Black"])
    bridge.ok("assign_material", name="Floor", material="Black")
    bridge.ok("set_world", color=[1.0, 1.0, 1.0], strength=1.0)
    incidence = 85.0
    bridge.ok("add_camera", name="Cam", location=[0.0, -60.0, 60.0 / math.tan(math.radians(incidence))],
              rotation=[incidence, 0.0, 0.0], lens=400.0)
    bridge.ok("render_final", path="water.exr", **QUICK)
    image = exr(bridge, "water")
    measured = float(image.reshape(-1, 3).mean(axis=0) @ LUMINANCE)
    expected = fresnel(math.cos(math.radians(incidence)), WATER_IOR)
    assert abs(measured - expected) < WATER_TOLERANCE, (measured, expected)


run(globals())
