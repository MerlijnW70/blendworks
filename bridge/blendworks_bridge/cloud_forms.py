"""Final cloud forms: volume switches and the cloud report."""

import json

from . import cloud_sheet, weather_objects, world_background


def stored(scene):
    world = scene.world
    if world is None or world.get(world_background.CLOUDS_PROPERTY) is None:
        return None
    return json.loads(world[world_background.CLOUDS_PROPERTY])


def switches(scene):
    found = []
    world = scene.world
    if world is not None and world.node_tree is not None:
        node = world.node_tree.nodes.get(cloud_sheet.SWITCH_NODE)
        if node is not None:
            found.append(node)
    for obj in weather_objects.objects(scene, ("cloud_shadow",)):
        for slot in obj.material_slots:
            if slot.material is not None and slot.material.node_tree is not None:
                node = slot.material.node_tree.nodes.get(cloud_sheet.SWITCH_NODE)
                if node is not None:
                    found.append(node)
    return found


def use_volumes(scene, bounces):
    """Render settings the cloud volumes need: ray-marched volumes and enough volume bounces."""
    cycles = scene.cycles
    cycles.volume_biased = True
    cycles.volume_bounces = max(cycles.volume_bounces, bounces)
    cycles.max_bounces = max(cycles.max_bounces, cycles.volume_bounces)
    return {"volume_bounces": cycles.volume_bounces, "volume_biased": True}


class FinalForm:
    """Inside render_final, clouds made with form auto render as volumes: the volumes show and the sheet steps back."""

    def __init__(self, scene):
        self.scene = scene
        self.saved = []
        settings = stored(scene)
        self.active = settings is not None and settings["form"] == "auto" and bool(settings["objects"]["volumes"])
        self.bounces = settings["bounces"] if self.active else 0

    def keep(self, owner, name):
        self.saved.append((owner, name, getattr(owner, name)))

    def __enter__(self):
        if not self.active:
            return self
        cycles = self.scene.cycles
        for name in ("volume_biased", "volume_bounces", "max_bounces"):
            self.keep(cycles, name)
        use_volumes(self.scene, self.bounces)
        for obj in weather_objects.objects(self.scene, ("cloud_volume", "rain_veil")):
            self.keep(obj, "hide_render")
            obj.hide_render = False
        for node in switches(self.scene):
            self.keep(node.outputs[0], "default_value")
            node.outputs[0].default_value = 1.0
        return self

    def __exit__(self, kind, error, trace):
        for owner, name, value in reversed(self.saved):
            setattr(owner, name, value)
        self.saved = []
        return False

    def report(self):
        return {"form": "volume", "volume_bounces": max(self.scene.cycles.volume_bounces, self.bounces)} if self.active else None


def cloud_report(scene):
    settings = stored(scene)
    if settings is None:
        return None
    return {"form": settings["form"], "layers": [layer["genus"] for layer in settings["layers"]], "cover": settings["cover"]}
