"""Close-up renders and their composition into a sheet."""

import os
from array import array
from math import atan

import bpy
from mathutils import Matrix, Vector

from judge_font import GLYPH_HEIGHT, draw_text, fit_text, printable, text_width
from judge_rig import basis, orientation
from judge_sheet import GAP, HEADER_LINE, HEADER_SCALE, LABEL_HEIGHT, LABEL_SCALE, MARGIN, TEXT, Canvas

HERO = ("hero", Vector((1.0, -1.0, 0.8)))
ANGLES = (("front-right", Vector((1.0, -1.0, 0.6))), ("back-left", Vector((-1.0, 1.0, 0.6))))
QUADRANTS = (("top-left", -1, 1), ("top-right", 1, 1), ("bottom-left", -1, -1), ("bottom-right", 1, -1))
UP = Vector((0.0, 0.0, 1.0))
FIT_MARGIN = 1.06
DISTANCE_IN_RADII = 3.0
PANEL_MAX = 600
QUADRANT_GAP = 4


MAX_POINTS = 60_000
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}


def world_points(depsgraph):
    points = array("d")
    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj.type not in GEOMETRY_TYPES:
            continue
        matrix = instance.matrix_world.copy()
        mesh = obj.to_mesh()
        try:
            if mesh is None or len(mesh.vertices) == 0:
                continue
            coordinates = array("f", [0.0]) * (len(mesh.vertices) * 3)
            mesh.vertices.foreach_get("co", coordinates)
            loops = array("i", [0]) * len(mesh.loops)
            mesh.loops.foreach_get("vertex_index", loops)
        finally:
            obj.to_mesh_clear()
        rows = [tuple(matrix[axis]) for axis in range(3)]
        for vertex in sorted(set(loops)):
            x, y, z = coordinates[vertex * 3], coordinates[vertex * 3 + 1], coordinates[vertex * 3 + 2]
            points.extend(row[0] * x + row[1] * y + row[2] * z + row[3] for row in rows)
    stride = max(1, len(points) // 3 // MAX_POINTS)
    if stride == 1:
        return points
    thinned = array("d")
    for start in range(0, len(points), 3 * stride):
        thinned.extend(points[start : start + 3])
    return thinned


class Framing:
    def __init__(self, rig, towards_viewer, points):
        self.rig = rig
        self.side, self.upward, self.depth = basis(towards_viewer, UP)
        self.distance = rig.radius * DISTANCE_IN_RADII
        self.position = rig.centre + self.depth * self.distance
        side, upward, depth, position = tuple(self.side), tuple(self.upward), tuple(self.depth), tuple(self.position)
        horizontal = []
        vertical = []
        for start in range(0, len(points), 3):
            offset = (points[start] - position[0], points[start + 1] - position[1], points[start + 2] - position[2])
            ahead = -(offset[0] * depth[0] + offset[1] * depth[1] + offset[2] * depth[2])
            horizontal.append((offset[0] * side[0] + offset[1] * side[1] + offset[2] * side[2]) / ahead)
            vertical.append((offset[0] * upward[0] + offset[1] * upward[1] + offset[2] * upward[2]) / ahead)
        if not horizontal:
            horizontal = vertical = [-1e-3, 1e-3]
        self.centre_x = (min(horizontal) + max(horizontal)) / 2
        self.centre_y = (min(vertical) + max(vertical)) / 2
        self.half = max(max(horizontal) - min(horizontal), max(vertical) - min(vertical), 1e-3) / 2 * FIT_MARGIN

    def window(self, quadrant=None):
        if quadrant is None:
            return self.centre_x, self.centre_y, self.half
        _, step_x, step_y = quadrant
        half = self.half / 2
        return self.centre_x + step_x * half, self.centre_y + step_y * half, half

    def aim(self, quadrant=None):
        centre_x, centre_y, half = self.window(quadrant)
        rig = self.rig
        camera = rig.camera.data
        camera.type = "PERSP"
        camera.sensor_fit = "HORIZONTAL"
        camera.angle = 2.0 * atan(half)
        camera.shift_x = centre_x / (2.0 * half)
        camera.shift_y = centre_y / (2.0 * half)
        camera.clip_start = max(self.distance - rig.radius * 1.1, self.distance * 1e-3)
        camera.clip_end = self.distance + rig.radius * 1.1
        rig.camera.matrix_world = Matrix.Translation(self.position) @ orientation(self.side, self.upward, self.depth)
        rig.place_lights(self.side, self.upward, self.depth)
        bpy.context.view_layer.update()


def shots(rig, points):
    yield HERO[0], Framing(rig, HERO[1].normalized(), points), None
    for angle, direction in ANGLES:
        framing = Framing(rig, direction.normalized(), points)
        for quadrant in QUADRANTS:
            yield f"{angle}-{quadrant[0]}", framing, quadrant


def render_shots(rig, points, folder):
    rendered = []
    for name, framing, quadrant in shots(rig, points):
        framing.aim(quadrant)
        path = os.path.join(folder, f"{name}.png")
        rig.scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        rendered.append({"name": name, "path": path})
    return rendered


def load_scaled(path, size):
    image = bpy.data.images.load(path, check_existing=False)
    if tuple(image.size) != (size, size):
        image.scale(size, size)
    pixels = array("f", [0.0]) * (size * size * 4)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels


def panel_sizes(resolution):
    quadrant = (min(resolution, PANEL_MAX) - QUADRANT_GAP) // 2
    return quadrant * 2 + QUADRANT_GAP, quadrant


def compose_closeups(images, resolution, header_lines, path):
    panel, quadrant = panel_sizes(resolution)
    by_name = {image["name"]: image["path"] for image in images}
    panels = [("hero three-quarter", None)] + [(f"{angle} 2 x 2", angle) for angle, _ in ANGLES]
    label_scale = next((scale for scale in (LABEL_SCALE, 2) if all(text_width(printable(label), scale) <= panel for label, _ in panels)), 1)
    header_width = max(text_width(printable(text), HEADER_SCALE) for text, _ in header_lines)
    header_height = MARGIN + HEADER_LINE * len(header_lines)
    width = MARGIN * 2 + max(panel * 3 + GAP * 2, header_width)
    height = header_height + GAP + LABEL_HEIGHT + panel + MARGIN
    canvas = Canvas(width, height)
    for index, (text, colour) in enumerate(header_lines):
        draw_text(canvas, fit_text(text, HEADER_SCALE, width - 2 * MARGIN), MARGIN, MARGIN + index * HEADER_LINE, HEADER_SCALE, colour)
    top = header_height + GAP
    label_top = top + (LABEL_HEIGHT - GLYPH_HEIGHT * label_scale) // 2 - 2
    for index, (label, angle) in enumerate(panels):
        left = MARGIN + index * (panel + GAP)
        draw_text(canvas, fit_text(label, label_scale, panel), left, label_top, label_scale, TEXT)
        if angle is None:
            canvas.paste_bottom_up(load_scaled(by_name[HERO[0]], panel), panel, panel, left, top + LABEL_HEIGHT)
            continue
        for name, step_x, step_y in QUADRANTS:
            tile_left = left + (0 if step_x < 0 else quadrant + QUADRANT_GAP)
            tile_top = top + LABEL_HEIGHT + (0 if step_y > 0 else quadrant + QUADRANT_GAP)
            canvas.paste_bottom_up(load_scaled(by_name[f"{angle}-{name}"], quadrant), quadrant, quadrant, tile_left, tile_top)
    canvas.save_png(path, "closeup-sheet")
    return width, height
