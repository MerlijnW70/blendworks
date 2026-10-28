import base64
import json
import os
import re
import shutil
import tempfile

import bpy
import numpy as np

from . import atmosphere_haze, device, exr_read
from .commands.images import write_image
from .errors import failed
from .preview import hex_color, id_color

LAYERS_FILE = "layers.exr"
SURFACE_SAMPLES = 16
SURFACE_SECONDS = 60.0
PREVIEW_SIZE = 512
PREVIEW_QUALITY = 85
FAR_DEPTH = 1e9
MIN_COVERAGE = 0.5
PASS_NAMES = ("depth", "normal", "albedo", "object_id")
PASS_FILES = {"depth": "depth", "normal": "normal", "albedo": "albedo", "object_id": "objects"}
SAMPLE_PASS = "Debug Sample Count"
BUDGET_TOLERANCE = 0.98
SAMPLE_PATTERN = re.compile(r"Sample (\d+)/(\d+)")
TIME_PATTERN = re.compile(r"^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$")


class SettingsScope:
    def __init__(self):
        self.saved = []

    def keep(self, owner, *names):
        for name in names:
            if hasattr(owner, name):
                self.saved.append((owner, name, getattr(owner, name)))

    def restore(self):
        for owner, name, value in self.saved:
            setattr(owner, name, value)
        self.saved = []


def keep_image_settings(scope, scene):
    scope.keep(scene.render.image_settings, "media_type", "file_format", "color_mode", "color_depth", "exr_codec", "compression", "quality")


def on_device(scene, choice, requested, work):
    try:
        with device.DeviceScope(scene, choice):
            return work(), choice
    except RuntimeError as error:
        if choice.device != "gpu" or device.requested_mode(requested) != "auto":
            raise failed(f"rendering on {choice.label()} failed: {error}") from error
        fallback = device.Choice("cpu", fallback=f"{choice.backend} did not render: {error}")
        with device.DeviceScope(scene, fallback):
            return work(), fallback


def enable_passes(scope, view_layer, passes, counting=False):
    scope.keep(view_layer, "use_pass_z", "use_pass_normal", "use_pass_cryptomatte_object")
    scope.keep(view_layer.cycles, "denoising_store_passes", "pass_debug_sample_count")
    view_layer.cycles.pass_debug_sample_count = counting
    view_layer.use_pass_z = "depth" in passes
    view_layer.use_pass_normal = "normal" in passes
    view_layer.use_pass_cryptomatte_object = "object_id" in passes
    view_layer.cycles.denoising_store_passes = "albedo" in passes


def render_layers(scene, view_layer, folder, passes, name=LAYERS_FILE, counting=False):
    scope = SettingsScope()
    keep_image_settings(scope, scene)
    scope.keep(scene.render, "filepath", "use_single_layer", "use_compositing")
    try:
        enable_passes(scope, view_layer, passes, counting)
        settings = scene.render.image_settings
        settings.media_type = "MULTI_LAYER_IMAGE"
        settings.file_format = "OPEN_EXR_MULTILAYER"
        settings.color_depth = "32"
        settings.exr_codec = "ZIP"
        scene.render.use_single_layer = True
        scene.render.use_compositing = False
        path = os.path.join(folder, name)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True, layer=view_layer.name)
    finally:
        scope.restore()
    if not os.path.isfile(path):
        raise failed("the render wrote no image")
    return path


class SurfacePasses:
    def __init__(self, scene, samples):
        self.scene = scene
        self.samples = min(samples, SURFACE_SAMPLES)
        self.scope = SettingsScope()

    def __enter__(self):
        cycles = self.scene.cycles
        self.scope.keep(cycles, "samples", "use_adaptive_sampling", "use_denoising", "time_limit")
        cycles.samples = self.samples
        cycles.use_adaptive_sampling = False
        cycles.use_denoising = False
        cycles.time_limit = SURFACE_SECONDS
        return self

    def __exit__(self, kind, error, trace):
        self.scope.restore()
        return False


def float_image(name, pixels):
    height, width = pixels.shape[:2]
    if pixels.shape[2] == 3:
        pixels = np.concatenate([pixels, np.ones((height, width, 1), dtype=np.float32)], axis=-1)
    image = bpy.data.images.new(name, width, height, alpha=True, float_buffer=True)
    image.pixels.foreach_set(np.ascontiguousarray(np.flipud(pixels), dtype=np.float32).ravel())
    return image


def combined(layers, layer):
    return layers.stack(f"{layer}.Combined", "RGBA")


def beauty_channels(layer, depth):
    names = {f"{layer}.Combined.{suffix}" for suffix in "RGBA"} | {f"{layer}.{SAMPLE_PASS}.X"}
    if depth:
        names.add(f"{layer}.Depth.Z")
    return names.__contains__


def pass_channels(layer, passes):
    prefixes = {
        "depth": f"{layer}.Depth.",
        "normal": f"{layer}.Normal.",
        "albedo": f"{layer}.Denoising Albedo.",
        "object_id": f"{layer}.CryptoObject00.",
    }
    wanted = tuple(prefixes[name] for name in passes)
    return lambda name: name.startswith(wanted)


def sample_statistics(layers, layer, cap):
    """Samples per pixel; Cycles writes each pixel's count as a share of the cap."""
    name = f"{layer}.{SAMPLE_PASS}.X"
    if not layers.has(name):
        return None
    counts = np.rint(layers.channel(name) * cap)
    return {"min": int(counts.min()), "max": int(counts.max()), "mean": round(float(counts.mean()), 3)}


def beauty_pixels(scene, camera, layers, layer, settings):
    rgba = combined(layers, layer)
    if settings is None:
        return rgba
    rgb = atmosphere_haze.depth_haze(scene, camera, rgba[..., :3], layers.channel(f"{layer}.Depth.Z"), settings)
    return np.concatenate([rgb, rgba[..., 3:]], axis=-1)


def render_hazed_still(scene, view_layer, camera, path, settings):
    folder = tempfile.mkdtemp(prefix="blendworks-haze-")
    try:
        layers = exr_read.read_exr(render_layers(scene, view_layer, folder, ("depth",)), beauty_channels(view_layer.name, True))
        image = float_image("blendworks_haze", beauty_pixels(scene, camera, layers, view_layer.name, settings))
        try:
            image.save_render(path, scene=scene)
        finally:
            bpy.data.images.remove(image)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def save_beauty(scene, image, path, file_format, depth, alpha):
    scope = SettingsScope()
    keep_image_settings(scope, scene)
    try:
        settings = scene.render.image_settings
        settings.media_type = "IMAGE"
        settings.file_format = file_format
        settings.color_mode = "RGBA" if alpha else "RGB"
        settings.color_depth = str(depth)
        if file_format == "OPEN_EXR":
            settings.exr_codec = "ZIP"
        else:
            settings.compression = 15
        image.save_render(path, scene=scene)
    finally:
        scope.restore()
    if not os.path.isfile(path):
        raise failed(f"the render could not be written to {os.path.basename(path)}")
    if file_format == "PNG":
        without_metadata(path)


def without_metadata(path):
    from .commands.render import without_text_chunks

    with open(path, "rb") as handle:
        data = handle.read()
    with open(path, "wb") as handle:
        handle.write(without_text_chunks(data))


def preview_image(path, folder):
    loaded = bpy.data.images.load(path, check_existing=False)
    try:
        width, height = loaded.size
        scale = min(1.0, PREVIEW_SIZE / max(width, height))
        loaded.scale(max(1, round(width * scale)), max(1, round(height * scale)))
        target = os.path.join(folder, "preview.jpg")
        write_image(loaded, target, "JPEG", 8, PREVIEW_QUALITY, False)
        size = list(loaded.size)
    finally:
        bpy.data.images.remove(loaded)
    with open(target, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return {"name": "preview", "width": size[0], "height": size[1], "mimeType": "image/jpeg", "data": data}


def write_view(name, pixels, path, data):
    image = float_image(f"blendworks_pass_{name}", pixels.astype(np.float32))
    try:
        write_image(image, path, "PNG", 16 if data else 8, 100, data)
    finally:
        bpy.data.images.remove(image)


def depth_view(depth):
    finite = depth < FAR_DEPTH
    if not finite.any():
        return np.ones(depth.shape + (3,), dtype=np.float32), None
    near, far = float(depth[finite].min()), float(depth[finite].max())
    spread = max(far - near, 1e-9)
    value = np.where(finite, (depth - near) / spread, 1.0)
    return np.repeat(value[..., None], 3, axis=-1), [round(near, 6), round(far, 6)]


def manifest_of(metadata, layer):
    for key, value in metadata.items():
        if key.startswith("cryptomatte/") and key.endswith("/name") and value == f"{layer}.CryptoObject":
            return json.loads(metadata.get(key[: -len("name")] + "manifest", "{}"))
    return {}


def hash_bits(text):
    bits = int(text, 16)
    exponent = (bits >> 23) & 0xFF
    return bits ^ (1 << 23) if exponent in (0, 0xFF) else bits


def object_view(layers, layer):
    ids = layers.channel(f"{layer}.CryptoObject00.r").view(np.uint32)
    coverage = layers.channel(f"{layer}.CryptoObject00.g")
    manifest = manifest_of(layers.metadata, layer)
    pixels = np.zeros(ids.shape + (3,), dtype=np.float32)
    legend = {}
    for name in sorted(manifest):
        mask = (ids == np.uint32(hash_bits(manifest[name]))) & (coverage >= MIN_COVERAGE)
        count = int(mask.sum())
        if count == 0:
            continue
        colour = id_color(len(legend))
        pixels[mask] = colour[:3]
        legend[name] = {"color": hex_color(colour), "hash": manifest[name], "pixels": count}
    return pixels, legend


def write_passes(layers, layer, passes, outputs, workspace):
    written = {}
    if "depth" in passes:
        view, span = depth_view(layers.channel(f"{layer}.Depth.Z"))
        written["depth"] = {"path": pass_path(outputs["depth"], workspace, view, True), "range": span}
    if "normal" in passes:
        normal = layers.stack(f"{layer}.Normal", "XYZ")
        written["normal"] = {"path": pass_path(outputs["normal"], workspace, normal * 0.5 + 0.5, True)}
    if "albedo" in passes:
        albedo = np.clip(layers.stack(f"{layer}.Denoising Albedo", "RGB"), 0.0, 1.0)
        written["albedo"] = {"path": pass_path(outputs["albedo"], workspace, albedo, False)}
    if "object_id" in passes:
        view, legend = object_view(layers, layer)
        written["object_id"] = {"path": pass_path(outputs["object_id"], workspace, view, True), "objects": legend}
    return written


def pass_path(path, workspace, pixels, data):
    write_view(os.path.basename(path), pixels, path, data)
    return workspace.relative(path)


def seconds_of(text):
    match = TIME_PATTERN.match(text.strip()) if text else None
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)


class SampleCounter:
    def __init__(self):
        self.most = None

    def __enter__(self):
        bpy.app.handlers.render_stats.append(self.seen)
        return self

    def __exit__(self, kind, error, trace):
        if self.seen in bpy.app.handlers.render_stats:
            bpy.app.handlers.render_stats.remove(self.seen)
        return False

    def seen(self, stats, *_rest):
        for done, _total in SAMPLE_PATTERN.findall(stats if isinstance(stats, str) else ""):
            self.most = max(self.most or 0, int(done))


def rendered_samples(counted, metadata, layer):
    if counted is not None:
        return counted
    value = metadata.get(f"cycles.{layer}.samples")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def budget_report(limit, cap, rendered, seconds, adaptive):
    if not limit:
        return {"seconds": None, "stopped": False, "sampling_seconds": seconds}
    short = rendered is not None and rendered < cap
    reached = seconds is not None and seconds >= limit * BUDGET_TOLERANCE
    stopped = short and (reached or not adaptive)
    return {"seconds": limit, "stopped": bool(stopped), "sampling_seconds": seconds}
