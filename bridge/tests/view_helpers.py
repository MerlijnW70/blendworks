import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
import numpy as np

from final_helpers import EXACT, channels

QUICK = dict(EXACT, samples=16, width=96, height=96, time_limit=120.0)


def render(bridge, name, shading="shaded", **arguments):
    settings = dict(QUICK, **arguments)
    result = bridge.ok("render_final", path=f"{name}.exr", shading=shading, **settings)
    return channels(bridge, f"{name}.exr"), result


def saturation(image):
    top = image.max(axis=-1)
    bottom = image.min(axis=-1)
    lit = top > 1e-3
    return (top[lit] - bottom[lit]) / top[lit]


def white_world(bridge, strength=1.0):
    bridge.ok("set_world", color=[1.0, 1.0, 1.0], strength=strength)


def look_down(name, height, resolution, ortho_scale=None):
    scene = bpy.context.scene
    data = bpy.data.cameras.new(name)
    data.lens = 50.0
    data.sensor_width = 36.0
    data.sensor_fit = "AUTO"
    data.clip_end = 1000.0
    if ortho_scale is not None:
        data.type = "ORTHO"
        data.ortho_scale = ortho_scale
    camera = bpy.data.objects.new(name, data)
    scene.collection.objects.link(camera)
    camera.location = (0.0, 0.0, height)
    scene.camera = camera
    scene.render.resolution_x = scene.render.resolution_y = resolution
    return camera


def mesh_object(name, coordinates, corners):
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(coordinates))
    mesh.vertices.foreach_set("co", coordinates.ravel())
    faces, size = corners.shape
    mesh.loops.add(corners.size)
    mesh.polygons.add(faces)
    mesh.loops.foreach_set("vertex_index", corners.ravel())
    mesh.polygons.foreach_set("loop_start", np.arange(faces, dtype=np.int32) * size)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def quad_grid(name, cells, size, wave=0.0, triangles=False):
    count = cells + 1
    axis = np.linspace(-size / 2.0, size / 2.0, count, dtype=np.float32)
    x, y = np.meshgrid(axis, axis)
    z = (wave * np.sin(x * 3.0) * np.cos(y * 2.0)).astype(np.float32)
    coordinates = np.stack([x, y, z], axis=-1).reshape(-1, 3)
    index = np.arange(count * count).reshape(count, count)
    a, b, c, d = index[:-1, :-1].ravel(), index[:-1, 1:].ravel(), index[1:, 1:].ravel(), index[1:, :-1].ravel()
    if triangles:
        return mesh_object(name, coordinates, np.stack([a, b, c, a, c, d], axis=-1).reshape(-1, 3))
    return mesh_object(name, coordinates, np.stack([a, b, c, d], axis=-1))


def line_coverage(bridge, name, **arguments):
    """Share of each pixel a wireframe's lines cover. Beside the wireframe, the same view renders in clay (no lines) and in
    clay of the line colour (all line), with the same samples, so the share is exact per pixel whatever the light, the
    specular sheen or the noise."""
    from blendworks_bridge import view_materials

    wire, result = render(bridge, name, shading="wireframe", **arguments)
    surface = {key: value for key, value in arguments.items() if not key.startswith("wire_")}
    clay, _ = render(bridge, f"{name}_clay", shading="clay", **surface)
    colour = view_materials.CLAY
    view_materials.CLAY = view_materials.LINE
    try:
        line, _ = render(bridge, f"{name}_line", shading="clay", **surface)
    finally:
        view_materials.CLAY = colour
    contrast = (clay - line).mean(axis=-1)
    share = np.where(contrast > 1e-3, (clay - wire).mean(axis=-1) / np.maximum(contrast, 1e-3), 0.0)
    return np.clip(share, 0.0, 1.0), result


def line_profile(coverage, row, centre, half):
    """Width in pixels and centre coordinate of a line crossing one row of a coverage image near a pixel coordinate."""
    start = int(round(centre)) - half
    pixels = np.arange(start, start + 2 * half)
    values = coverage[row, start : start + 2 * half]
    width = float(values.sum())
    return width, float((values * (pixels + 0.5)).sum() / max(width, 1e-9))


def peak_memory_gib():
    """Highest resident memory of this process so far, in GiB, on Windows and Linux."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD), ("peak", ctypes.c_size_t), ("working", ctypes.c_size_t)] + [(f"more{i}", ctypes.c_size_t) for i in range(6)]

        counters = Counters()
        counters.size = ctypes.sizeof(counters)
        kernel, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.size)
        return counters.peak / 2**30
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
