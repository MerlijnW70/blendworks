import math

import bpy
import numpy
from mathutils.bvhtree import BVHTree

TERRAIN = {"size": [40.0, 40.0], "resolution": 81, "height": 16.0, "seed": 4, "scale": 28.0, "octaves": 4, "hurst": 0.7, "mode": "ridged", "ridge_offset": 1.0, "attributes": ["slope", "height"]}


def make_ground(bridge, name="Ground", size=10.0):
    bridge.ok("add_primitive", type="plane", name=name, size=size)


def make_bolt(bridge, name="Bolt", location=(100.0, 100.0, 0.0)):
    bridge.ok("add_primitive", type="cylinder", name=name, radius=0.05, depth=0.1, segments=8, location=list(location))


def make_terrain(bridge, name="Terrain", **extra):
    return bridge.ok("heightfield", name=name, **{**TERRAIN, **extra})


def copies(prefix):
    bpy.context.view_layer.update()
    return sorted((obj for obj in bpy.data.objects if obj.name.startswith(f"{prefix}_") and obj.type == "MESH"), key=lambda obj: obj.name)


def locations(prefix):
    return numpy.array([list(obj.matrix_world.translation) for obj in copies(prefix)])


def scales(prefix):
    return numpy.array([obj.matrix_world.to_scale()[0] for obj in copies(prefix)])


def axes(prefix):
    return numpy.array([list(obj.matrix_world.to_3x3().col[2].normalized()) for obj in copies(prefix)])


def smallest_distance(points):
    gaps = numpy.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    gaps[numpy.arange(len(points)), numpy.arange(len(points))] = numpy.inf
    return float(gaps.min())


def clearance_ratio(points, sizes, smallest_size, min_distance):
    gaps = numpy.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    needed = min_distance * (sizes[:, None] + sizes[None, :]) / (2.0 * smallest_size)
    gaps[numpy.arange(len(points)), numpy.arange(len(points))] = numpy.inf
    return float((gaps / needed).min())


def face_data(name, points):
    bpy.context.view_layer.update()
    obj = bpy.data.objects[name]
    tree = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    mesh = obj.data
    slopes = []
    faces = []
    for point in points:
        _, _, index, _ = tree.find_nearest(point)
        slopes.append(math.degrees(math.acos(max(-1.0, min(1.0, mesh.polygons[index].normal.z)))))
        faces.append(index)
    return numpy.array(slopes), numpy.array(faces)


def steepest_face(name):
    mesh = bpy.data.objects[name].data
    return max(math.degrees(math.acos(max(-1.0, min(1.0, polygon.normal.z)))) for polygon in mesh.polygons)


def splat(points, extent, pixels=256, radius=3):
    image = numpy.zeros((pixels, pixels))
    axis = numpy.arange(pixels)
    for x, y in points:
        cx, cy = (x / extent + 0.5) * pixels, (y / extent + 0.5) * pixels
        image[(axis[:, None] - cy) ** 2 + (axis[None, :] - cx) ** 2 <= radius * radius] = 1.0
    return image


def repetition_peak(image, minimum_shift=16, minimum_overlap=0.25):
    values = image - image.mean()
    height, width = values.shape
    padded = numpy.zeros((2 * height, 2 * width))
    padded[:height, :width] = values
    spectrum = numpy.fft.rfft2(padded)
    correlation = numpy.fft.irfft2(spectrum * numpy.conj(spectrum), s=padded.shape)
    ones = numpy.zeros_like(padded)
    ones[:height, :width] = 1.0
    ones_spectrum = numpy.fft.rfft2(ones)
    overlap = numpy.rint(numpy.fft.irfft2(ones_spectrum * numpy.conj(ones_spectrum), s=padded.shape))
    shifts_y = numpy.fft.fftfreq(2 * height, 1.0 / (2 * height)).astype(int)
    shifts_x = numpy.fft.fftfreq(2 * width, 1.0 / (2 * width)).astype(int)
    far = numpy.hypot(shifts_y[:, None], shifts_x[None, :]) > minimum_shift
    enough = overlap >= minimum_overlap * height * width
    usable = far & enough
    normalised = correlation[usable] / overlap[usable] / values.var()
    return float(normalised.max())


def jittered_grid(count, extent, jitter, rng):
    side = round(math.sqrt(count))
    step = extent / side
    cells = (numpy.arange(side) + 0.5) * step - extent / 2
    x, y = numpy.meshgrid(cells, cells)
    centres = numpy.column_stack([x.ravel(), y.ravel()])
    return centres + rng.uniform(-jitter, jitter, centres.shape) * step
