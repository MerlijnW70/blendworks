import os
import tempfile
from array import array

import bpy

from judge_common import JudgeError, stopwatch

GPU_BACKENDS = ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI")
CPU = "CPU"
AUTO = "AUTO"
TEST_SIZE = 16
TEST_GREY = 0.5
TEST_BRIGHTNESS = (0.6, 0.85)
MAX_NAME = 120


def cycles_preferences():
    return bpy.context.preferences.addons["cycles"].preferences


def backend_devices(backend):
    preferences = cycles_preferences()
    try:
        preferences.compute_device_type = backend
    except TypeError:
        return None
    preferences.refresh_devices()
    return [device for device in preferences.devices if device.type == backend]


def device_backend(text):
    backend = text.upper()
    if backend not in (CPU, AUTO) and backend not in GPU_BACKENDS:
        raise JudgeError("usage", f"--device must be CPU, AUTO or one of {', '.join(GPU_BACKENDS)}")
    return backend


def backend_order(text):
    backends = [backend.strip().upper() for backend in text.split(",") if backend.strip()]
    unknown = [backend for backend in backends if backend not in GPU_BACKENDS]
    if unknown:
        raise JudgeError("usage", f"unknown backends: {', '.join(unknown)}")
    return backends


def apply_device(scene, backend):
    if backend == CPU:
        scene.cycles.device = "CPU"
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        scene.cycles.denoising_use_gpu = False
        return {"backend": CPU, "devices": []}
    devices = backend_devices(backend)
    if not devices:
        raise JudgeError("gpu_unavailable", f"no {backend} device starts inside the sandbox")
    for device in cycles_preferences().devices:
        device.use = device.type == backend
    scene.cycles.device = "GPU"
    scene.cycles.denoiser = "OPTIX" if backend == "OPTIX" else "OPENIMAGEDENOISE"
    scene.cycles.denoising_use_gpu = True
    return {"backend": backend, "devices": [device.name[:MAX_NAME] for device in devices]}


def emission_material():
    material = bpy.data.materials.new("device-test")
    nodes = material.node_tree.nodes
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (TEST_GREY, TEST_GREY, TEST_GREY, 1.0)
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def test_scene():
    scene = bpy.data.scenes.new("device-test")
    mesh = bpy.data.meshes.new("device-test")
    mesh.from_pydata([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)], [], [(0, 1, 2, 3)])
    material = emission_material()
    mesh.materials.append(material)
    plane = bpy.data.objects.new("device-test", mesh)
    scene.collection.objects.link(plane)
    camera_data = bpy.data.cameras.new("device-test-camera")
    camera = bpy.data.objects.new("device-test-camera", camera_data)
    camera.location = (0.0, 0.0, 3.0)
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 2
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = True
    scene.render.resolution_x = TEST_SIZE
    scene.render.resolution_y = TEST_SIZE
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    return scene, (plane, camera), (mesh, material, camera_data)


def remove_test_scene(scene, objects, blocks):
    bpy.data.scenes.remove(scene)
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh, material, camera_data = blocks
    bpy.data.meshes.remove(mesh)
    bpy.data.materials.remove(material)
    bpy.data.cameras.remove(camera_data)


def mean_red(path):
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    pixels = array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    reds = pixels[0::4]
    return sum(reds) / len(reds) if reds else 0.0


def render_test(scene, backend, folder):
    try:
        apply_device(scene, backend)
    except JudgeError as error:
        return error.message
    path = os.path.join(folder, f"device-test-{backend.lower()}.png")
    scene.render.filepath = path
    try:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            bpy.ops.render.render(write_still=True)
    except RuntimeError as error:
        first_line = (str(error).strip().splitlines() or [type(error).__name__])[0]
        return f"the test render failed: {first_line[:200]}"
    if not os.path.isfile(path):
        return "the test render wrote no image"
    brightness = mean_red(path)
    low, high = TEST_BRIGHTNESS
    if not low <= brightness <= high:
        return f"the test render came out wrong (brightness {brightness:.3f}, expected {low} to {high})"
    return None


def test_render(backend, folder):
    scene, objects, blocks = test_scene()
    try:
        return render_test(scene, backend, folder)
    finally:
        remove_test_scene(scene, objects, blocks)


def probe_backends(order, folder):
    results = []
    for backend in order:
        devices = backend_devices(backend)
        if devices is None:
            results.append({"backend": backend, "devices": [], "usable": False, "reason": "not in this Blender build"})
            continue
        names = [device.name[:MAX_NAME] for device in devices]
        if not names:
            results.append({"backend": backend, "devices": [], "usable": False, "reason": "no device found"})
            continue
        problem = test_render(backend, folder)
        results.append({"backend": backend, "devices": names, "usable": problem is None, "reason": problem or ""})
        if problem is None:
            break
    return results


def resolve_backend(requested, order_text):
    if requested != AUTO:
        return requested, {"probes": [], "probeSeconds": None}
    timer = stopwatch()
    with tempfile.TemporaryDirectory(prefix="blendworks-device-") as folder:
        probes = probe_backends(backend_order(order_text), folder)
    found = {"probes": probes, "probeSeconds": timer()}
    usable = next((probe["backend"] for probe in probes if probe["usable"]), None)
    if usable is None:
        raise JudgeError("gpu_unavailable", "no GPU backend works inside the sandbox", found)
    return usable, found


def use_device(scene, backend, found):
    try:
        return apply_device(scene, backend)
    except JudgeError as error:
        error.extra = found
        raise
