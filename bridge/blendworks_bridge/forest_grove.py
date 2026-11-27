"""Calibration of impostor brightness in a grove: a small stand of trees on a ground, seen from the camera's direction
under the scene's world and lights, rendered once as real trees and once as cards (with their sun-facing shadow cards).
In a stand the trees shade each other and the ground as a forest does, which a lone tree does not show; the gain that
makes the cards' mean colour that of the trees is what removes the step where trees turn into cards."""
import math
import os
import shutil
import tempfile

import bpy
import numpy
from mathutils import Matrix, Vector

from . import exr_read, impostors
from .edge_order import canonical_edges
from .errors import failed
from .forest_cards import GAIN_RANGE, LUMINANCE, card_mesh

ROWS = 4
COLUMNS = 6
PIXELS = 96
SAMPLES = 24


class Grove:
    def __init__(self, scene, collections, spheres, frames, spacing, sun, seed):
        self.scene, self.collections, self.spheres, self.frames = scene, collections, spheres, frames
        self.spacing, self.sun = spacing, sun
        rng = numpy.random.default_rng([int(seed), 41])
        count = ROWS * COLUMNS
        grid = numpy.array([[column - (COLUMNS - 1) / 2.0, row - (ROWS - 1) / 2.0] for row in range(ROWS) for column in range(COLUMNS)])
        self.bases = numpy.column_stack([(grid + rng.uniform(-0.3, 0.3, (count, 2))) * spacing, numpy.zeros(count)])
        self.variants = rng.integers(0, len(collections), count)
        self.turns = rng.uniform(0.0, 2.0 * math.pi, count)

    def run(self, material, toward):
        folder = tempfile.mkdtemp(prefix="blendworks-grove-")
        probe = bpy.data.scenes.new("blendworks forest grove")
        made, meshes = [], []
        try:
            self.prepare(probe, toward, made, meshes)
            trees = self.render(probe, folder, "trees")
            for obj in made:
                if obj.instance_type == "COLLECTION":
                    obj.hide_render = True
            self.cards(probe, material, toward, made, meshes)
            cards = self.render(probe, folder, "cards")
        finally:
            for obj in made:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if isinstance(data, bpy.types.Camera):
                    bpy.data.cameras.remove(data)
            for mesh in meshes:
                bpy.data.meshes.remove(mesh)
            bpy.data.scenes.remove(probe)
            shutil.rmtree(folder, ignore_errors=True)
        return compare(trees, cards)

    def prepare(self, probe, toward, made, meshes):
        render = probe.render
        render.engine = "CYCLES"
        probe.cycles.device = "CPU"
        probe.cycles.samples = SAMPLES
        probe.cycles.use_denoising = False
        probe.cycles.use_adaptive_sampling = False
        probe.cycles.seed = 0
        probe.cycles.transparent_max_bounces = 128
        render.film_transparent = True
        render.resolution_x, render.resolution_y = 2 * PIXELS, PIXELS
        render.resolution_percentage = 100
        render.use_compositing = False
        render.image_settings.file_format = "OPEN_EXR"
        render.image_settings.color_depth = "32"
        render.image_settings.color_mode = "RGBA"
        probe.world = self.scene.world
        for light in (obj for obj in self.scene.objects if obj.type == "LIGHT" and not obj.hide_render):
            probe.collection.objects.link(light)
        for index, base in enumerate(self.bases):
            empty = bpy.data.objects.new(f"grove tree {index}", None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = self.collections[self.variants[index]]
            empty.matrix_world = Matrix.Translation(Vector(base)) @ Matrix.Rotation(self.turns[index], 4, "Z")
            probe.collection.objects.link(empty)
            made.append(empty)
        ground = bpy.data.meshes.new("grove ground")
        side = (max(ROWS, COLUMNS) + 4) * self.spacing
        ground.from_pydata([(-side, -side, 0.0), (side, -side, 0.0), (side, side, 0.0), (-side, side, 0.0)], [], [(0, 1, 2, 3)])
        canonical_edges(ground)
        meshes.append(ground)
        plane = bpy.data.objects.new("grove ground", ground)
        plane.is_holdout = True
        probe.collection.objects.link(plane)
        made.append(plane)
        height = max(height for _, _, height in self.spheres)
        data = bpy.data.cameras.new("grove camera")
        data.type = "ORTHO"
        data.ortho_scale = (COLUMNS + 1) * self.spacing
        data.clip_end = 100.0 * side
        camera = bpy.data.objects.new("grove camera", data)
        self.eye = numpy.array([0.0, 0.0, height / 2.0]) - numpy.asarray(toward) * 20.0 * side
        camera.matrix_world = Matrix.Translation(Vector(self.eye)) @ Vector(tuple(toward)).to_track_quat("-Z", "Y").to_matrix().to_4x4()
        probe.collection.objects.link(camera)
        probe.camera = camera
        made.append(camera)

    def card_trees(self, viewer):
        trees = {"pivot": [], "turn": [], "view": [], "half": [], "variant": []}
        for base, variant, turn in zip(self.bases, self.variants, self.turns):
            centre, radius, _ = self.spheres[variant]
            cos, sin = math.cos(turn), math.sin(turn)
            pivot = base + numpy.array([cos * centre[0] - sin * centre[1], sin * centre[0] + cos * centre[1], centre[2]])
            trees["pivot"].append(pivot)
            trees["turn"].append(turn)
            trees["view"].append(impostors.local_view(pivot, turn, viewer(pivot)))
            trees["half"].append(radius * impostors.CELL_MARGIN)
            trees["variant"].append(int(variant))
        return trees

    def cards(self, probe, material, toward, made, meshes):
        sets = [("grove cards", lambda pivot: pivot - numpy.asarray(toward) * 1e6, False)]
        if self.sun is not None:
            sets.append(("grove shadows", lambda pivot: pivot + self.sun * 1e6, True))
        for name, viewer, shadow_only in sets:
            mesh = card_mesh(name, self.card_trees(viewer), self.frames, len(self.collections))
            mesh.materials.append(material)
            meshes.append(mesh)
            obj = bpy.data.objects.new(name, mesh)
            if shadow_only:
                for flag in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
                    setattr(obj, flag, False)
            elif self.sun is not None:
                obj.visible_shadow = True
            probe.collection.objects.link(obj)
            made.append(obj)

    def render(self, probe, folder, name):
        path = os.path.join(folder, name + ".exr")
        probe.render.filepath = path
        bpy.ops.render.render(write_still=True, scene=probe.name)
        if not os.path.isfile(path):
            raise failed("the grove calibration wrote no image")
        return numpy.asarray(exr_read.read_exr(path).stack("", "RGBA"), dtype=numpy.float64)


def compare(trees, cards):
    tree_mean = trees[..., :3].sum(axis=(0, 1)) / max(float(trees[..., 3].sum()), 1e-9)
    card_mean = cards[..., :3].sum(axis=(0, 1)) / max(float(cards[..., 3].sum()), 1e-9)
    gain = numpy.clip(tree_mean / numpy.maximum(card_mean, 1e-6), *GAIN_RANGE)
    step = abs(float(card_mean @ LUMINANCE) / max(float(tree_mean @ LUMINANCE), 1e-9) - 1.0)
    return {"gain": [round(float(value), 4) for value in gain], "step_before": round(step, 4),
            "tree_colour": [round(float(v), 5) for v in tree_mean], "card_colour": [round(float(v), 5) for v in card_mean],
            "coverage": {"trees": round(float(trees[..., 3].mean()), 4), "cards": round(float(cards[..., 3].mean()), 4)}}
