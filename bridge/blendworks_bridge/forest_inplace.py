"""Calibration of impostor brightness in the scene itself. The trees nearest beyond the switch are rendered from the
camera once as real trees and once as cards, with everything else in the scene as it is (land, sky, sun, haze), and a
third time without them. Over the pixels where they show, the ratio of the two mean colours is the gain that removes the
step where trees turn into cards (when they cover at least 1000 pixels of a 256 px wide frame; fewer
are too few to trust, and the grove's gain stays); renders with the gain applied refine it, up to four times, and measure the step that is left."""
import shutil
import tempfile

import bpy
import numpy

from . import exr_read, render_outputs
from .forest_cards import GAIN_RANGE, LUMINANCE

WIDTH = 256
LEAST_PIXELS = 1000
SAMPLES = 16
ROUNDS = 4
SETTLED = 0.02


def render(scene, view_layer, folder, name, passes=()):
    path = render_outputs.render_layers(scene, view_layer, folder, list(passes), name + ".exr")
    image = exr_read.read_exr(path)
    layer = f"{view_layer.name}.Combined"
    colour = numpy.asarray(image.stack(layer, "RGB") if image.has(layer + ".R") else image.stack("", "RGB"), dtype=numpy.float64)
    depth = image.channel(f"{view_layer.name}.Depth.Z") if "depth" in passes else None
    return colour, depth


class InScene:
    def __init__(self, ctx, camera):
        self.ctx, self.camera = ctx, camera

    def __enter__(self):
        scene = self.ctx.scene
        self.scope = render_outputs.SettingsScope()
        self.scope.keep(scene, "camera")
        self.scope.keep(scene.render, "engine", "resolution_x", "resolution_y", "resolution_percentage", "use_border", "film_transparent")
        self.scope.keep(scene.cycles, "device", "samples", "seed", "use_denoising", "use_adaptive_sampling", "time_limit")
        aspect = scene.render.resolution_y / max(scene.render.resolution_x, 1)
        scene.camera = self.camera
        scene.render.engine = "CYCLES"
        scene.render.resolution_x = WIDTH
        scene.render.resolution_y = max(16, int(round(WIDTH * aspect)))
        scene.render.resolution_percentage = 100
        scene.render.use_border = False
        scene.render.film_transparent = False
        scene.cycles.device = "CPU"
        scene.cycles.samples = SAMPLES
        scene.cycles.seed = 0
        scene.cycles.use_denoising = False
        scene.cycles.use_adaptive_sampling = False
        scene.cycles.time_limit = 0.0
        self.folder = tempfile.mkdtemp(prefix="blendworks-forest-scene-")
        return self

    def __exit__(self, kind, error, trace):
        self.scope.restore()
        shutil.rmtree(self.folder, ignore_errors=True)
        return False

    def frame(self, name, passes=()):
        return render(self.ctx.scene, self.ctx.view_layer, self.folder, name, passes)


def calibrate(ctx, camera, make_trees, make_cards, set_gain, gain, reach):
    """make_trees adds the forest as real trees, make_cards the same forest with the band past the switch as cards; both
    return the objects they add, which are removed after. The pixels compared are those whose depth lies in reach."""
    with InScene(ctx, camera) as probe:
        made = make_trees()
        try:
            trees, depth = probe.frame("trees", ("depth",))
        finally:
            remove(made)
        made = make_cards()
        try:
            cards, _ = probe.frame("cards")
            shows = (depth >= reach[0]) & (depth <= reach[1])
            if shows.sum() < LEAST_PIXELS:
                return {"gain": list(gain), "pixels": int(shows.sum()), "step_before": None, "step_after": None}
            tree_mean, card_mean = trees[shows].mean(axis=0), cards[shows].mean(axis=0)
            after = card_mean
            for _ in range(ROUNDS):
                correction = numpy.clip(tree_mean / numpy.maximum(after, 1e-9), *GAIN_RANGE)
                gain = numpy.clip(numpy.asarray(gain) * correction, *GAIN_RANGE)
                set_gain(gain)
                after = probe.frame("after")[0][shows].mean(axis=0)
                if abs(float(after @ LUMINANCE) / float(tree_mean @ LUMINANCE) - 1.0) < SETTLED:
                    break
        finally:
            remove(made)
    tree_light = float(tree_mean @ LUMINANCE)
    return {"gain": [round(float(v), 4) for v in gain], "pixels": int(shows.sum()),
            "step_before": round(abs(float(card_mean @ LUMINANCE) / tree_light - 1.0), 4),
            "step_after": round(abs(float(after @ LUMINANCE) / tree_light - 1.0), 4)}


def remove(objects):
    for obj in objects:
        if obj is None:
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
