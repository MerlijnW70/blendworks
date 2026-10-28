import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
import numpy as np

from blendworks_bridge import exr_read, render_outputs

CPU = {"device": "cpu"}
EXACT = {"denoise": False, "noise_threshold": 0.0, "time_limit": 600.0, "preview": False, "device": "cpu"}


def emissive(bridge, name, strength):
    if bpy.data.materials.get(name) is None:
        bridge.ok("add_material", name=name, base_color=[0.0, 0.0, 0.0], roughness=1.0, emission_color=[1.0, 1.0, 1.0], emission_strength=strength)
    return name


def card(bridge, name, centre, width, height, material, rotation=(90.0, 0.0, 0.0)):
    bridge.ok("add_primitive", type="plane", name=name, size=1.0, location=list(centre), rotation=list(rotation))
    bridge.ok("transform", name=name, scale=[width, height, 1.0])
    bridge.ok("assign_material", name=name, material=material)


def split_card(bridge, name, distance, width, x=0.0, z=0.0, white=4.0):
    card(bridge, f"{name}_white", (x - width / 4.0, distance, z), width / 2.0, width, emissive(bridge, f"white_{white}", white))
    card(bridge, f"{name}_black", (x + width / 4.0, distance, z), width / 2.0, width, emissive(bridge, "black", 0.0))


def camera_on_y(bridge, name="Cam", lens=50.0, location=(0.0, 0.0, 0.0)):
    bridge.ok("add_camera", name=name, location=list(location), rotation=[90.0, 0.0, 0.0], lens=lens)


def linear(bridge, path):
    return exr_read.read_exr(os.path.join(bridge.workspace, path)).stack("", "RGB").mean(axis=-1)


def png_linear(bridge, path):
    image = bpy.data.images.load(os.path.join(bridge.workspace, path), check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        width, height = image.size
        values = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(values)
    finally:
        bpy.data.images.remove(image)
    encoded = np.flipud(values.reshape(height, width, 4))[..., :3]
    decoded = np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)
    return decoded.mean(axis=-1)


def edge_sharpness(rows):
    steps = np.abs(np.diff(rows, axis=1))
    span = rows.max(axis=1) - rows.min(axis=1)
    return float(np.mean(steps.max(axis=1) / np.maximum(span, 1e-9)))


def halves_contrast(image, margin=0.3):
    height, width = image.shape
    top, bottom = int(height * margin), int(height * (1.0 - margin))
    left = image[top:bottom, int(width * 0.1) : int(width * 0.4)]
    right = image[top:bottom, int(width * 0.6) : int(width * 0.9)]
    return float(left.mean() - right.mean()), float(left.mean()), float(right.mean())


def channels(bridge, path):
    return exr_read.read_exr(os.path.join(bridge.workspace, path)).stack("", "RGB")


def diffuse(bridge, name, value):
    if bpy.data.materials.get(name) is None:
        bridge.ok("add_material", name=name, base_color=[value] * 3, roughness=1.0)
    return name


def noisy_wall(bridge):
    """A split bright and dark wall lit only by a small area lamp: noisy at a few samples."""
    bridge.ok("set_world", color=[0.0, 0.0, 0.0], strength=0.0)
    for side, value in ((-1, 0.8), (1, 0.05)):
        card(bridge, f"Wall{side}", (side * 1.5, 6.0, 0.0), 3.0, 6.0, diffuse(bridge, f"wall_{side}", value))
    bridge.ok("add_light", type="area", name="Lamp", location=[0.0, 3.0, 2.5], rotation=[50.0, 0.0, 0.0], energy=300.0, size=0.5)
    camera_on_y(bridge)


class Recorded:
    """Records the render settings in force each time a Blender render starts."""

    def __init__(self):
        self.calls = []

    def __enter__(self):
        self.original = render_outputs.render_layers
        recorded = self

        def render_layers(scene, view_layer, folder, passes, *rest, **named):
            cycles = scene.cycles
            recorded.calls.append(
                {
                    "denoising": cycles.use_denoising,
                    "layer_denoising": view_layer.cycles.use_denoising,
                    "denoiser": cycles.denoiser,
                    "inputs": cycles.denoising_input_passes,
                    "adaptive": cycles.use_adaptive_sampling,
                    "time_limit": cycles.time_limit,
                    "samples": cycles.samples,
                }
            )
            return recorded.original(scene, view_layer, folder, passes, *rest, **named)

        render_outputs.render_layers = render_layers
        return self

    def __exit__(self, kind, error, trace):
        render_outputs.render_layers = self.original
        return False
