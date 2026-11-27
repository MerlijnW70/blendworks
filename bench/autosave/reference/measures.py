import ctypes
import hashlib
import os
import sys
import time

import bpy
import numpy

CALIBRATION_ROUNDS = 5


def peak_memory_bytes():
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
        kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return int(counters.PeakWorkingSetSize)
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def calibration_seconds():
    """CPU seconds of a fixed single-threaded workload of Python loops and numpy array maths, the two kinds of work the
    tools do; the best of several rounds, so a busy machine inflates it as little as the tools it scales."""
    best = None
    for _ in range(CALIBRATION_ROUNDS):
        started = time.process_time()
        generator = numpy.random.default_rng(7)
        values = generator.random(2_000_000)
        for _ in range(12):
            values = numpy.sqrt(values * 1.0001 + 0.5) * numpy.sort(values)[::-1]
        total = 0.0
        for index in range(3_000_000):
            total += (index % 7) * 0.5
        spent = time.process_time() - started
        best = spent if best is None else min(best, spent)
    return best


def array_of(collection, field, kind, width):
    data = numpy.empty(len(collection) * width, dtype=kind)
    if len(collection):
        collection.foreach_get(field, data)
    return data


def attribute_arrays(mesh):
    found = {}
    for attribute in mesh.attributes:
        if attribute.name.startswith(".") or attribute.data_type in ("STRING",):
            continue
        width = {"FLOAT": 1, "INT": 1, "BOOLEAN": 1, "INT8": 1, "FLOAT2": 2, "INT32_2D": 2, "FLOAT_VECTOR": 3,
                 "FLOAT_COLOR": 4, "BYTE_COLOR": 4, "QUATERNION": 4, "FLOAT4X4": 16}.get(attribute.data_type)
        if width is None:
            continue
        field = "value" if width == 1 or attribute.data_type in ("QUATERNION", "FLOAT4X4") else (
            "vector" if attribute.data_type in ("FLOAT2", "FLOAT_VECTOR", "INT32_2D") else "color")
        kind = numpy.int32 if attribute.data_type in ("INT", "INT32_2D", "INT8") else (
            numpy.bool_ if attribute.data_type == "BOOLEAN" else numpy.float32)
        found[f"{attribute.domain}:{attribute.name}"] = array_of(attribute.data, field, kind, width)
    return found


def mesh_measure(obj):
    mesh = obj.data
    coordinates = array_of(mesh.vertices, "co", numpy.float32, 3)
    loops = array_of(mesh.loops, "vertex_index", numpy.int32, 1)
    starts = array_of(mesh.polygons, "loop_start", numpy.int32, 1)
    digest = hashlib.sha256()
    digest.update(coordinates.tobytes())
    digest.update(loops.tobytes())
    digest.update(starts.tobytes())
    attributes = attribute_arrays(mesh)
    for name in sorted(attributes):
        digest.update(name.encode("utf-8"))
        digest.update(attributes[name].tobytes())
    points = coordinates.reshape(-1, 3).astype(numpy.float64)
    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.polygons),
        "loops": len(mesh.loops),
        "attributes": sorted(attributes),
        "hash": digest.hexdigest()[:16],
        "sum": [round(float(value), 3) for value in points.sum(axis=0)] if len(points) else [0.0, 0.0, 0.0],
        "spread": [round(float(value), 4) for value in points.std(axis=0)] if len(points) else [0.0, 0.0, 0.0],
    }, points


def geometry(scene):
    """Every object's own data and transform, hashed exactly, with counts and coordinate moments that survive a change of
    floating-point order; and the evaluated scene's instance count, which counts what scattering and ground cover make."""
    objects = {}
    for obj in sorted(scene.objects, key=lambda item: item.name):
        entry = {"type": obj.type, "matrix": hashlib.sha256(numpy.array(obj.matrix_world, dtype=numpy.float32).tobytes()).hexdigest()[:16]}
        if obj.type == "MESH":
            measured, _ = mesh_measure(obj)
            entry.update(measured)
        if obj.type == "POINTCLOUD":
            coordinates = array_of(obj.data.points, "co", numpy.float32, 3)
            entry.update({"points": len(obj.data.points), "hash": hashlib.sha256(coordinates.tobytes()).hexdigest()[:16]})
        modifiers = [modifier.type for modifier in obj.modifiers]
        if modifiers:
            entry["modifiers"] = modifiers
        objects[obj.name] = entry
    depsgraph = bpy.context.evaluated_depsgraph_get()
    instances = 0
    evaluated_vertices = 0
    for instance in depsgraph.object_instances:
        if instance.is_instance:
            instances += 1
        elif instance.object.type == "MESH":
            evaluated_vertices += len(instance.object.data.vertices)
    totals = {
        "objects": len(objects),
        "vertices": sum(entry.get("vertices", 0) for entry in objects.values()),
        "faces": sum(entry.get("faces", 0) for entry in objects.values()),
        "instances": instances,
        "evaluated_vertices": evaluated_vertices,
    }
    return {"totals": totals, "objects": objects}


def image_statistics(path):
    image = bpy.data.images.load(path, check_existing=False)
    try:
        width, height = image.size
        pixels = numpy.empty(width * height * 4, dtype=numpy.float32)
        image.pixels.foreach_get(pixels)
    finally:
        bpy.data.images.remove(image)
    rgb = pixels.reshape(-1, 4)[:, :3].astype(numpy.float64)
    luminance = rgb @ numpy.array([0.2126, 0.7152, 0.0722])
    return {
        "size": [width, height],
        "mean": [round(float(value), 5) for value in rgb.mean(axis=0)],
        "std": [round(float(value), 5) for value in rgb.std(axis=0)],
        "luminance_percentiles": [round(float(value), 5) for value in numpy.percentile(luminance, [1, 10, 50, 90, 99])],
        "hash": hashlib.sha256(pixels.tobytes()).hexdigest()[:16],
    }


def image_difference(path_a, path_b):
    arrays = []
    for path in (path_a, path_b):
        image = bpy.data.images.load(path, check_existing=False)
        pixels = numpy.empty(image.size[0] * image.size[1] * 4, dtype=numpy.float32)
        image.pixels.foreach_get(pixels)
        bpy.data.images.remove(image)
        arrays.append(pixels.reshape(-1, 4)[:, :3].astype(numpy.float64))
    difference = numpy.abs(arrays[0] - arrays[1])
    return {"mean_abs": float(difference.mean()), "p99_abs": float(numpy.percentile(difference, 99)), "max_abs": float(difference.max())}


def environment():
    return {"platform": sys.platform, "blender": bpy.app.version_string, "threads": os.cpu_count()}
