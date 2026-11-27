"""Far clips that cover the scene. A camera's far clip is raised to reach the farthest corner of every visible object's
bounding box, so land, clouds and haze tens of kilometres out are never cut off. A clip_end that camera_setup was given
is the user's own and stays."""
from mathutils import Vector

from .limits import MAX_LENGTH
from .util import GEOMETRY_TYPES

EXPLICIT = "blendworks_clip_explicit"
LEAST_CLIP = 10_000.0
MARGIN = 1.02


def scene_reach(scene, view_layer, origin):
    """Distance from origin to the farthest bounding-box corner of a visible object, in metres."""
    farthest = 0.0
    for obj in scene.objects:
        if obj.type not in GEOMETRY_TYPES or not obj.visible_get(view_layer=view_layer):
            continue
        matrix = obj.matrix_world
        for corner in obj.bound_box:
            farthest = max(farthest, (matrix @ Vector(corner) - origin).length)
    return farthest


def covering_clip(scene, view_layer, camera, least=0.0):
    needed = scene_reach(scene, view_layer, camera.matrix_world.translation) * MARGIN
    return min(max(needed, least), MAX_LENGTH.plain())


def is_explicit(camera):
    return bool(camera.data.get(EXPLICIT, False))


def mark_explicit(data, explicit):
    if explicit:
        data[EXPLICIT] = True
    elif EXPLICIT in data:
        del data[EXPLICIT]


class ClipCovers:
    """Raise the camera's far clip to cover the scene while a render runs, unless the clip was set explicitly."""

    def __init__(self, scene, view_layer, camera):
        self.scene, self.view_layer, self.camera = scene, view_layer, camera
        self.saved = None
        self.report = {}

    def __enter__(self):
        data = self.camera.data
        if is_explicit(self.camera):
            return self
        needed = covering_clip(self.scene, self.view_layer, self.camera)
        if needed > data.clip_end:
            self.saved = data.clip_end
            data.clip_end = needed
            self.report = {"clip_end_raised": {"from": round(self.saved, 3), "to": round(needed, 3)}}
        return self

    def __exit__(self, kind, error, trace):
        if self.saved is not None:
            self.camera.data.clip_end = self.saved
        return False


def raise_all(scene, view_layer):
    """Raise every camera's far clip that is not explicit to cover the scene; returns the cameras changed."""
    changed = {}
    for camera in (item for item in scene.objects if item.type == "CAMERA"):
        if is_explicit(camera):
            continue
        needed = covering_clip(scene, view_layer, camera)
        if needed > camera.data.clip_end:
            camera.data.clip_end = needed
            changed[camera.name] = round(needed, 3)
    return changed

