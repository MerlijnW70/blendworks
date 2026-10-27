import os

import bpy

from .errors import bad_args, failed

ENVIRONMENT = "BLENDWORKS_DEVICE"
MODES = ("auto", "gpu", "cpu")
BACKENDS = ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI")


def requested_mode(explicit=None):
    if explicit is not None:
        return explicit
    value = os.environ.get(ENVIRONMENT, "")
    text = value.strip().lower()
    if text == "":
        return "auto"
    if text not in MODES:
        raise bad_args(f'{ENVIRONMENT} must be auto, gpu or cpu, not "{value}"')
    return text


def cycles_preferences():
    addon = bpy.context.preferences.addons.get("cycles")
    return addon.preferences if addon is not None else None


def probe_backends():
    preferences = cycles_preferences()
    if preferences is None:
        return []
    probes = []
    for backend in BACKENDS:
        try:
            devices = preferences.get_devices_for_type(backend)
        except (TypeError, ValueError, RuntimeError):
            probes.append({"backend": backend, "devices": [], "usable": False, "reason": "not in this Blender build"})
            continue
        names = [device.name for device in devices if device.type == backend]
        reason = "" if names else "no device found"
        probes.append({"backend": backend, "devices": names, "usable": bool(names), "reason": reason})
    return probes


def no_gpu_reason(probes):
    tried = [f"{probe['backend']}: {probe['reason'] or 'not usable'}" for probe in probes]
    return f"no usable GPU ({'; '.join(tried)})" if tried else "no usable GPU (no backend was probed)"


class Choice:
    def __init__(self, device, backend=None, names=(), fallback=None):
        self.device = device
        self.backend = backend
        self.names = list(names)
        self.fallback = fallback

    def report(self):
        return {"device": self.device, "backend": self.backend, "names": self.names, "fallback": self.fallback}

    def label(self):
        if self.device == "gpu":
            return f"gpu {self.backend} ({', '.join(self.names)})"
        return "cpu" if self.fallback is None else f"cpu (auto fell back to the CPU: {self.fallback})"


def choose_device(mode, probe=None):
    if mode == "cpu":
        return Choice("cpu")
    probes = (probe or probe_backends)()
    for backend in BACKENDS:
        for found in probes:
            if found["backend"] == backend and found["usable"] and found["devices"]:
                return Choice("gpu", backend, found["devices"])
    reason = no_gpu_reason(probes)
    if mode == "gpu":
        raise failed(f"{ENVIRONMENT}=gpu, but {reason}")
    return Choice("cpu", fallback=reason)


class DeviceScope:
    def __init__(self, scene, choice):
        self.scene = scene
        self.choice = choice
        self.preferences = cycles_preferences()
        self.saved_device = scene.cycles.device
        self.saved_backend = None
        self.saved_use = {}

    def __enter__(self):
        if self.choice.device == "cpu" or self.preferences is None:
            self.scene.cycles.device = "CPU"
            return self
        self.saved_backend = self.preferences.compute_device_type
        self.preferences.compute_device_type = self.choice.backend
        self.preferences.get_devices_for_type(self.choice.backend)
        self.saved_use = {device.id: device.use for device in self.preferences.devices}
        for device in self.preferences.devices:
            device.use = device.type == self.choice.backend
        self.scene.cycles.device = "GPU"
        return self

    def __exit__(self, kind, error, trace):
        self.scene.cycles.device = self.saved_device
        if self.saved_backend is not None:
            for device in self.preferences.devices:
                if device.id in self.saved_use:
                    device.use = self.saved_use[device.id]
            self.preferences.compute_device_type = self.saved_backend
        return False
