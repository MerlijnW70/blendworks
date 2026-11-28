import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import run

from blendworks_bridge import abrasion, rock_shape, stone_shape
from blendworks_bridge.handler import Context

TRANSPORTS = {"talus": (0.05, 0.2), "shore": (0.4, 0.55), "river": (0.75, 0.9)}
SEEDS = (3, 11)
EDGE_OVER_FLAT = 4.0
EDGE_WEAR_SPREAD = 0.06
TALUS_FRESH_AT_LEAST = 0.15


def granite(bridge):
    bridge.ok("material_procedural", name="Granite", stone={"lithology": "granite"})
    return Context(bridge.handler, None)


def test_each_history_class_has_its_stated_roundness_sphericity_and_flatness(bridge):
    """Stones of each class (two transports, two seeds) fall within the class's ranges in rock_shape.HISTORIES, the classes
    rise in mean roundness from talus to river, talus blocks keep fresh fracture faces and river cobbles none. Proven by
    building every class without abrasion (MAX_PASSES 0): the river cobbles then stay angular, under their range."""
    context = granite(bridge)
    found = {name: [] for name in TRANSPORTS}
    for name, transports in TRANSPORTS.items():
        for transport in transports:
            for seed in SEEDS:
                stone, _, shape = stone_shape.build_stone(context, f"{name}_{transport}_{seed}", transport, seed, "Granite")
                assert shape["history"] == name
                assert rock_shape.in_ranges(shape, name), (name, transport, seed, shape)
                found[name].append(shape)
    means = {name: np.mean([shape["roundness"] for shape in shapes]) for name, shapes in found.items()}
    assert means["talus"] < means["shore"] < means["river"], means
    assert min(shape["fresh_share"] for shape in found["talus"]) >= TALUS_FRESH_AT_LEAST, [shape["fresh_share"] for shape in found["talus"]]
    assert all(shape["fresh_share"] == 0.0 for shape in found["river"])
    assert all(shape["passes"] == 0 for shape in found["talus"]) and all(shape["passes"] > 0 for shape in found["river"])


def test_the_roundness_measure_reads_wadell_on_shapes_of_known_corners(bridge):
    """A rounded square whose corners have radius r of the inscribed radius reads r (Wadell's definition), an ellipse of axes
    2:1 reads 0.5 (its end radius b^2/a over b), a circle 1 and a sharp square at most 0.1."""
    def rounded_square(share, steps=200):
        points = []
        for x, y in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            centre = np.array([x, y]) * (1.0 - share)
            start = np.arctan2(y, x)
            for angle in np.linspace(start - np.pi / 4, start + np.pi / 4, steps):
                points.append(centre + share * np.array([np.cos(angle), np.sin(angle)]))
        return np.column_stack([np.array(points), np.zeros(len(points))])

    for share in (0.15, 0.3, 0.5, 0.8):
        assert abs(rock_shape.roundness(rounded_square(share)) - share) < 0.03, share
    angle = np.linspace(0.0, 2.0 * np.pi, 400, endpoint=False)
    assert abs(rock_shape.roundness(np.column_stack([2.0 * np.cos(angle), np.sin(angle), 0.0 * angle])) - 0.5) < 0.03
    assert rock_shape.roundness(np.column_stack([np.cos(angle), np.sin(angle), 0.0 * angle])) > 0.98
    assert rock_shape.roundness(np.array([[1.0, 1.0, 0.0], [-1.0, 1.0, 0.0], [-1.0, -1.0, 0.0], [1.0, -1.0, 0.0]])) <= 0.1


def curvature(points, triangles):
    edges = abrasion.edge_table(triangles)
    degree = np.maximum(np.bincount(edges.ravel(), minlength=len(points)).astype(float), 1.0)
    total = np.zeros_like(points)
    np.add.at(total, edges[:, 0], points[edges[:, 1]])
    np.add.at(total, edges[:, 1], points[edges[:, 0]])
    normals = abrasion.vertex_normals(points, triangles)
    return np.abs(np.einsum("ij,ij->i", total / degree[:, None] - points, normals)), normals


def abraded(bridge, name, seed):
    bridge.ok("add_primitive", type="cube", name=name, size=1.0)
    bridge.ok("abrade", name=name, amount=0.0, edge_length=0.05)
    before, triangles = stone_shape.mesh_arrays(bpy.data.objects[name])
    bent, normals = curvature(before, triangles)
    bridge.ok("abrade", name=name, amount=0.4, seed=seed, edge_length=0.05)
    after, after_triangles = stone_shape.mesh_arrays(bpy.data.objects[name])
    assert len(after) == len(before) and np.array_equal(after_triangles, triangles)
    return before, bent, -np.einsum("ij,ij->i", after - before, normals)


def test_abrasion_wears_edges_and_corners_first_and_unevenly(bridge):
    """On a refined cube, abrade removes material (inward movement along the normal) from the most curved tenth of the
    vertices at least EDGE_OVER_FLAT times as much as from the flattest half, so it is no uniform smoothing; and the same cube
    worn with another seed loses a different amount at each edge vertex (mean difference above EDGE_WEAR_SPREAD of the mean
    removal), since a seeded field speeds wear up on some stretches of edge and slows it on others. Proven by moving every
    vertex inward by the same step (the ratio falls to 1) and by a wear field of no spread (the seeds then agree)."""
    before, bent, removal = abraded(bridge, "Block", 5)
    _, _, other = abraded(bridge, "Other", 6)
    order = np.argsort(bent)
    curved, flat = order[-len(order) // 10:], order[: len(order) // 2]
    assert removal[curved].mean() > EDGE_OVER_FLAT * max(removal[flat].mean(), 1e-6), (removal[curved].mean(), removal[flat].mean())
    on_edge = np.sum(np.abs(np.abs(before) - 0.5) < 1e-6, axis=1) >= 2
    spread = np.abs(removal[on_edge] - other[on_edge]).mean() / removal[on_edge].mean()
    assert spread > EDGE_WEAR_SPREAD, spread


run(globals())
