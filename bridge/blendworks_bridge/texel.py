import contextlib
import math

import bpy
import numpy

from .errors import bad_args
from .operators import only_selected, operator_context
from .util import rounded

TINY_AREA = 1e-12
MAX_MARGIN_PACKS = 4
MARGIN_TOLERANCE = 0.05
MARGIN_AIM = 0.01
CALIBRATION_SPREAD = 2.0
HULL_EXTENT = 0.9


def uv_area(points):
    total = 0.0
    for index in range(1, len(points) - 1):
        a, b, c = points[0], points[index], points[index + 1]
        total += abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0
    return total


def world_area(points):
    total = 0.0
    for index in range(1, len(points) - 1):
        total += (points[index] - points[0]).cross(points[index + 1] - points[0]).length / 2.0
    return total


def face_areas(obj, layer):
    mesh = obj.data
    matrix = obj.matrix_world
    world = [matrix @ vertex.co for vertex in mesh.vertices]
    areas = []
    for polygon in mesh.polygons:
        uvs = [layer.data[index].uv for index in polygon.loop_indices]
        corners = [world[index] for index in polygon.vertices]
        areas.append((uv_area(uvs), world_area(corners)))
    return areas


def density(obj, layer, texture_size):
    areas = face_areas(obj, layer)
    total_uv = sum(item[0] for item in areas)
    total_world = sum(item[1] for item in areas)
    faces = [texture_size * math.sqrt(uv / area) for uv, area in areas if area > TINY_AREA]
    if total_world <= TINY_AREA or not faces:
        return {"texture_size": texture_size, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "texture_size": texture_size,
        "mean": rounded(texture_size * math.sqrt(total_uv / total_world), 3),
        "min": rounded(min(faces), 3),
        "max": rounded(max(faces), 3),
    }


def mean_density(obj, layer, texture_size):
    areas = face_areas(obj, layer)
    total_uv = sum(item[0] for item in areas)
    total_world = sum(item[1] for item in areas)
    if total_uv <= 0.0 or total_world <= TINY_AREA:
        raise bad_args(f"{obj.name} has no UV or surface area to measure a texel density on")
    return texture_size * math.sqrt(total_uv / total_world)


def scale_uvs(obj, layer, factor):
    for item in layer.data:
        item.uv = (item.uv[0] * factor, item.uv[1] * factor)
    obj.data.update()


def scale_to_density(obj, layer, target, texture_size):
    factor = target / mean_density(obj, layer, texture_size)
    scale_uvs(obj, layer, factor)
    return factor


@contextlib.contextmanager
def multi_edit_mode(view_layer, objects):
    active = objects[0]
    with only_selected(view_layer, active, objects):
        with bpy.context.temp_override(**operator_context(active, objects)):
            bpy.ops.object.mode_set(mode="EDIT")
            try:
                bpy.ops.mesh.reveal()
                bpy.ops.mesh.select_all(action="SELECT")
                yield
            finally:
                bpy.ops.object.mode_set(mode="OBJECT")


def average_island_scale(view_layer, objects):
    with multi_edit_mode(view_layer, objects):
        bpy.ops.uv.average_islands_scale(scale_uv=False, shear=False)


def run_pack(view_layer, objects, margin, rotate, scale, rotate_method, shape_method, margin_method):
    with multi_edit_mode(view_layer, objects):
        bpy.ops.uv.pack_islands(
            udim_source="CLOSEST_UDIM",
            rotate=rotate,
            rotate_method=rotate_method,
            scale=scale,
            margin_method=margin_method,
            margin=margin,
            shape_method=shape_method,
        )
    for obj in objects:
        obj.data.update()


class Atlas:
    def __init__(self, objects):
        self.objects = objects
        self.starts = []
        for obj in objects:
            polygons = obj.data.polygons
            starts = numpy.empty(len(polygons), dtype=numpy.int64)
            polygons.foreach_get("loop_start", starts)
            self.starts.append(starts)
        self.initial = self.read()

    def show(self, layouts):
        if self.shown is not layouts:
            self.write(layouts)

    def pack(self, view_layer, margin, rotate, rotate_method, shape_method, margin_method):
        run_pack(view_layer, self.objects, margin, rotate, True, rotate_method, shape_method, margin_method)
        return self.read()

    def read(self):
        layouts = []
        for obj in self.objects:
            data = obj.data.uv_layers.active.uv
            flat = numpy.empty(len(data) * 2, dtype=numpy.float64)
            data.foreach_get("vector", flat)
            layouts.append(flat.reshape(-1, 2))
        self.shown = layouts
        return layouts

    def write(self, layouts):
        for obj, uv in zip(self.objects, layouts):
            obj.data.uv_layers.active.uv.foreach_set("vector", uv.reshape(-1))
            obj.data.update()
        self.shown = layouts

    def area(self, layouts):
        total = 0.0
        for uv, starts in zip(layouts, self.starts):
            if len(starts) == 0:
                continue
            following = numpy.roll(uv, -1, axis=0)
            ends = numpy.append(starts[1:], len(uv)) - 1
            following[ends] = uv[starts]
            cross = uv[:, 0] * following[:, 1] - following[:, 0] * uv[:, 1]
            total += 0.5 * float(numpy.abs(numpy.add.reduceat(cross, starts)).sum())
        return total


class ExtentModel:
    def __init__(self):
        self.samples = {}

    def remember(self, group, method, added, extent):
        self.samples.setdefault((group, method), []).append((added, extent))

    def fitted(self, group, method):
        own = self.samples.get((group, method), [])
        kin = [self.kin(group, lambda kept: kept != method and kept[1] == method[1]), self.kin(group, lambda kept: kept != method and kept[0] == method[0]), self.kin(group, lambda kept: kept != method)]
        if len(own) >= 2:
            return line(own)
        if own:
            added, extent = own[-1]
            for samples in kin:
                if len(samples) >= 2:
                    intercept, slope = line(samples)
                    ratio = extent / (intercept + slope * added)
                    return intercept * ratio, slope * ratio
            return extent, 0.0
        packed = next((line(samples) for samples in kin if samples), None)
        if packed is None or any(kept_group == group and kept_method[0] != "AABB" for kept_group, kept_method in self.samples):
            return packed
        intercept, slope = packed
        return intercept * HULL_EXTENT, slope * HULL_EXTENT

    def known(self, group):
        return any(kept_group == group for kept_group, _ in self.samples)

    def kin(self, group, alike):
        return [sample for (kept_group, kept_method), samples in self.samples.items() if kept_group == group and alike(kept_method) for sample in samples]


def line(samples):
    added, extent = samples[-1]
    spread = [(abs(earlier - added), earlier, earlier_extent) for earlier, earlier_extent in samples[:-1] if abs(earlier - added) > 1e-9 * added]
    for _, earlier, earlier_extent in sorted(spread, reverse=True):
        slope = (extent - earlier_extent) / (added - earlier)
        if slope >= 0.0:
            return extent - slope * added, slope
    return extent, 0.0


def margin_root(model, margin):
    intercept, slope = model
    if intercept <= 0.0 or margin * slope >= 1.0:
        return None
    return margin * intercept / (1.0 - margin * slope)


MEMORY = []


@contextlib.contextmanager
def margin_memory():
    MEMORY.append(ExtentModel())
    try:
        yield
    finally:
        MEMORY.pop()


def calibrate(view_layer, atlas, margin, memory, group, before):
    for added in (margin, margin * CALIBRATION_SPREAD):
        atlas.show(atlas.initial)
        covered = atlas.area(atlas.pack(view_layer, added, False, "ANY", "AABB", "FRACTION"))
        if covered <= TINY_AREA:
            return
        scale = math.sqrt(covered / before)
        memory.remember(group, ("AABB", None), added / scale, 1.0 / scale)


def search_margin(view_layer, atlas, margin, rotate, rotate_method, shape_method, memory):
    before = atlas.area(atlas.initial)
    group = tuple(obj.name for obj in atlas.objects)
    if not memory.known(group):
        calibrate(view_layer, atlas, margin, memory, group, before)
    method = (shape_method, rotate_method if rotate else None)
    model = memory.fitted(group, method)
    root = None if model is None else margin_root(model, margin)
    added = margin if root is None else root * (1.0 + MARGIN_AIM)
    best = None
    for _ in range(MAX_MARGIN_PACKS):
        atlas.show(atlas.initial)
        layouts = atlas.pack(view_layer, added, rotate, rotate_method, shape_method, "ADD")
        covered = atlas.area(layouts)
        if covered <= TINY_AREA:
            break
        extent = math.sqrt(before / covered)
        memory.remember(group, method, added, extent)
        effective = added / extent
        if effective >= margin and (best is None or covered > best[0]):
            best = (covered, layouts)
        if margin <= effective <= margin * (1.0 + MARGIN_TOLERANCE):
            break
        root = margin_root(memory.fitted(group, method), margin)
        added = margin * extent if root is None else root * (1.0 + MARGIN_AIM)
    return best


def pack_to_margin(view_layer, objects, margin, rotate, rotate_method, shape_method, memory):
    atlas = Atlas(objects)
    best = None
    if shape_method != "AABB" and atlas.area(atlas.initial) > TINY_AREA:
        best = search_margin(view_layer, atlas, margin, rotate, rotate_method, shape_method, memory)
    if best is None:
        atlas.show(atlas.initial)
        atlas.pack(view_layer, margin, rotate, rotate_method, shape_method, "FRACTION")
        return
    atlas.show(best[1])


def pack(view_layer, objects, margin, rotate, scale, rotate_method="ANY", shape_method="CONCAVE"):
    if MEMORY and scale and margin > 0.0:
        pack_to_margin(view_layer, objects, margin, rotate, rotate_method, shape_method, MEMORY[-1])
        return
    run_pack(view_layer, objects, margin, rotate, scale, rotate_method, shape_method, "FRACTION")
