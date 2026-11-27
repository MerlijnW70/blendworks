"""Octahedral impostors of trees. A tree is drawn into an atlas of frames x frames views over the upper hemisphere, laid out
by the hemi-octahedral map (u, v) -> direction (x, y, 1 - |x| - |y|) with x = (u + v) / 2 and y = (u - v) / 2. All views
render at once: one linked copy per frame, turned so that its view direction faces a single orthographic camera above
them. The render's passes give the albedo times ambient occlusion with the coverage as alpha, the normal in the tree's own
frame and the depth from the crown's centre plane. A card shows the frame nearest to the direction it is seen from."""
import math
import os
import shutil
import tempfile

import bpy
import numpy
from mathutils import Matrix, Vector

from . import exr_read
from .errors import failed

LAYER = "ViewLayer"
BAKE_SAMPLES = 16
DILATE_STEPS = 6
CELL_MARGIN = 1.02
ALPHA_FLOOR = 1e-3
OCCLUSION_REACH = 0.45


def decode(u, v):
    x = (u + v) / 2.0
    y = (u - v) / 2.0
    z = 1.0 - numpy.abs(x) - numpy.abs(y)
    direction = numpy.stack([x, y, numpy.maximum(z, 0.0)], axis=-1)
    return direction / numpy.linalg.norm(direction, axis=-1, keepdims=True)


def encode(direction):
    direction = numpy.asarray(direction, dtype=numpy.float64)
    flat = direction.copy()
    flat[..., 2] = numpy.maximum(flat[..., 2], 0.0)
    total = numpy.abs(flat[..., 0]) + numpy.abs(flat[..., 1]) + flat[..., 2]
    x = flat[..., 0] / total
    y = flat[..., 1] / total
    return x + y, x - y


def frame_direction(frames, column, row):
    u = (column + 0.5) / frames * 2.0 - 1.0
    v = (row + 0.5) / frames * 2.0 - 1.0
    return decode(numpy.asarray(u), numpy.asarray(v))


def view_axes(direction):
    """Right, up and toward-viewer axes, in the tree's frame, of the image seen from direction (tree to viewer)."""
    toward = numpy.asarray(direction, dtype=numpy.float64)
    up = numpy.array([0.0, 0.0, 1.0]) - toward[2] * toward
    if numpy.linalg.norm(up) < 1e-6:
        up = numpy.array([0.0, 1.0, 0.0]) - toward[1] * toward
    up = up / numpy.linalg.norm(up)
    right = numpy.cross(up, toward)
    return right, up, toward


def bounds_sphere(objects):
    points = []
    for obj in objects:
        local = numpy.empty(len(obj.data.vertices) * 3, dtype=numpy.float32)
        obj.data.vertices.foreach_get("co", local)
        matrix = numpy.array(obj.matrix_local, dtype=numpy.float64)
        points.append(local.reshape(-1, 3).astype(numpy.float64) @ matrix[:3, :3].T + matrix[:3, 3])
    points = numpy.concatenate(points)
    centre = (points.min(axis=0) + points.max(axis=0)) / 2.0
    return centre, float(numpy.linalg.norm(points - centre, axis=1).max()), float(points[:, 2].max() - points[:, 2].min())


def dilate(colour, alpha, steps):
    """Spread colours into transparent pixels so filtering at a silhouette never blends with black."""
    filled = alpha > ALPHA_FLOOR
    colour = colour.copy()
    for _ in range(steps):
        total = numpy.zeros_like(colour)
        count = numpy.zeros(filled.shape)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shifted = numpy.roll(filled, (dy, dx), axis=(0, 1))
            total += numpy.roll(colour, (dy, dx), axis=(0, 1)) * shifted[..., None]
            count += shifted
        grow = ~filled & (count > 0)
        colour[grow] = total[grow] / count[grow][:, None]
        filled = filled | grow
    return colour


class Bake:
    """A private scene that renders the atlas of one tree collection."""

    def __init__(self, collection, frames, pixels, centre, radius):
        self.collection, self.frames, self.pixels = collection, frames, pixels
        self.centre, self.radius = Vector(centre), radius
        self.cell = 2.0 * radius * CELL_MARGIN

    def render(self):
        folder = tempfile.mkdtemp(prefix="blendworks-impostor-")
        scene = bpy.data.scenes.new("blendworks impostor bake")
        world = bpy.data.worlds.new("blendworks impostor bake")
        made = []
        try:
            self.prepare(scene, world, made)
            path = os.path.join(folder, "atlas.exr")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True, scene=scene.name)
            if not os.path.isfile(path):
                raise failed("the impostor bake wrote no image")
            return self.read(path)
        finally:
            for obj in made:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0:
                    bpy.data.cameras.remove(data)
            bpy.data.scenes.remove(scene)
            bpy.data.worlds.remove(world)
            shutil.rmtree(folder, ignore_errors=True)

    def prepare(self, scene, world, made):
        size = self.frames * self.pixels
        render = scene.render
        render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = BAKE_SAMPLES
        scene.cycles.use_denoising = False
        scene.cycles.use_adaptive_sampling = False
        scene.cycles.seed = 0
        scene.cycles.transparent_max_bounces = 64
        render.film_transparent = True
        render.resolution_x = render.resolution_y = size
        render.resolution_percentage = 100
        render.use_compositing = False
        render.use_sequencer = False
        settings = render.image_settings
        settings.media_type = "MULTI_LAYER_IMAGE"
        settings.file_format = "OPEN_EXR_MULTILAYER"
        settings.color_depth = "32"
        scene.world = world
        world.light_settings.distance = OCCLUSION_REACH * self.radius
        layer = scene.view_layers[0]
        layer.name = LAYER
        layer.use_pass_diffuse_color = True
        layer.use_pass_normal = True
        layer.use_pass_z = True
        layer.use_pass_ambient_occlusion = True
        for column in range(self.frames):
            for row in range(self.frames):
                copy = bpy.data.objects.new(f"impostor frame {column} {row}", None)
                copy.instance_type = "COLLECTION"
                copy.instance_collection = self.collection
                copy.matrix_world = self.frame_matrix(column, row)
                scene.collection.objects.link(copy)
                made.append(copy)
        data = bpy.data.cameras.new("impostor camera")
        data.type = "ORTHO"
        data.ortho_scale = self.frames * self.cell
        data.clip_start = 0.01
        data.clip_end = 8.0 * self.radius
        camera = bpy.data.objects.new("impostor camera", data)
        camera.location = (self.frames * self.cell / 2.0, self.frames * self.cell / 2.0, 4.0 * self.radius)
        scene.collection.objects.link(camera)
        scene.camera = camera
        made.append(camera)

    def rotation(self, column, row):
        right, up, toward = view_axes(frame_direction(self.frames, column, row))
        return numpy.array([right, up, toward])

    def frame_matrix(self, column, row):
        turn = Matrix(self.rotation(column, row).tolist()).to_4x4()
        cell_centre = Vector(((column + 0.5) * self.cell, (row + 0.5) * self.cell, 0.0))
        return Matrix.Translation(cell_centre) @ turn @ Matrix.Translation(-self.centre)

    def read(self, path):
        image = exr_read.read_exr(path)
        flip = numpy.flipud
        alpha = flip(image.channel(f"{LAYER}.Combined.A")).astype(numpy.float64)
        albedo = flip(image.stack(f"{LAYER}.Diffuse Color", "RGB")).astype(numpy.float64)
        occlusion = flip(image.stack(f"{LAYER}.Ambient Occlusion", "RGB")).astype(numpy.float64).mean(axis=-1)
        normal = flip(image.stack(f"{LAYER}.Normal", "XYZ")).astype(numpy.float64)
        depth = flip(image.channel(f"{LAYER}.Depth.Z")).astype(numpy.float64)
        cover = numpy.maximum(alpha, ALPHA_FLOOR)[..., None]
        colour = albedo / cover * numpy.clip(occlusion / cover[..., 0], 0.0, 1.0)[..., None]
        local = self.local_normals(normal)
        solid = alpha > 0.5
        centre_depth = 4.0 * self.radius
        relative = numpy.where(solid, numpy.clip((centre_depth - depth) / self.radius, -1.0, 1.0), 0.0)
        colour = dilate(colour, alpha, DILATE_STEPS)
        local = dilate(local, alpha, DILATE_STEPS)
        return {"colour": colour, "alpha": alpha, "normal": local, "depth": relative}

    def local_normals(self, normal):
        size = self.pixels
        local = numpy.zeros_like(normal)
        for column in range(self.frames):
            for row in range(self.frames):
                turn = self.rotation(column, row)
                block = normal[row * size:(row + 1) * size, column * size:(column + 1) * size]
                local[row * size:(row + 1) * size, column * size:(column + 1) * size] = block @ turn
        length = numpy.linalg.norm(local, axis=-1, keepdims=True)
        return numpy.where(length > 1e-6, local / numpy.maximum(length, 1e-6), numpy.array([0.0, 0.0, 1.0]))


def atlas_images(name, atlases):
    """Two packed float images holding every variant's atlas side by side: colour with alpha, and normal with depth."""
    colour = numpy.concatenate([numpy.dstack([entry["colour"], entry["alpha"]]) for entry in atlases], axis=1)
    normal = numpy.concatenate([numpy.dstack([entry["normal"] * 0.5 + 0.5, entry["depth"] * 0.5 + 0.5]) for entry in atlases], axis=1)
    return packed_image(f"{name}_colour", colour, False), packed_image(f"{name}_normal", normal, True)


def packed_image(name, pixels, data):
    height, width = pixels.shape[:2]
    image = bpy.data.images.new(name, width, height, alpha=True, float_buffer=True, is_data=data)
    image.pixels.foreach_set(numpy.ascontiguousarray(pixels, dtype=numpy.float32).ravel())
    image.file_format = "OPEN_EXR"
    image.pack()
    return image


def blend_frames(frames, direction):
    """The four frames around a view direction and their bilinear weights over the atlas grid."""
    u, v = encode(direction)
    grid_x = float(numpy.clip((u + 1.0) / 2.0 * frames - 0.5, 0.0, frames - 1.0))
    grid_y = float(numpy.clip((v + 1.0) / 2.0 * frames - 0.5, 0.0, frames - 1.0))
    column, row = min(int(grid_x), max(frames - 2, 0)), min(int(grid_y), max(frames - 2, 0))
    fx, fy = grid_x - column, grid_y - row
    right, up = min(column + 1, frames - 1), min(row + 1, frames - 1)
    return [(column, row, (1.0 - fx) * (1.0 - fy)), (right, row, fx * (1.0 - fy)), (column, up, (1.0 - fx) * fy), (right, up, fx * fy)]


def spin(turn):
    cos, sin = math.cos(turn), math.sin(turn)
    return numpy.array([[cos, -sin, 0.0], [sin, cos, 0.0], [0.0, 0.0, 1.0]])


def card_corners(pivot, turn, direction, half):
    """Corners of a card centred on the crown's pivot, facing the viewer: the image axes of the view direction (in the
    tree's frame) turned by the tree's rotation about z, half a cell wide each way."""
    right, up, _ = view_axes(direction)
    right, up = spin(turn) @ right, spin(turn) @ up
    pivot = numpy.asarray(pivot)
    return [pivot - right * half - up * half, pivot + right * half - up * half, pivot + right * half + up * half, pivot - right * half + up * half]


def local_view(pivot, turn, eye):
    """Unit direction from the tree to the eye in the tree's own frame, never below its horizon."""
    toward = spin(-turn) @ (numpy.asarray(eye, dtype=numpy.float64) - numpy.asarray(pivot, dtype=numpy.float64))
    toward[2] = max(toward[2], 0.0)
    length = numpy.linalg.norm(toward)
    return toward / length if length > 1e-9 else numpy.array([0.0, 0.0, 1.0])
