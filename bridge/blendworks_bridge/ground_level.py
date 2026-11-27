"""The low ground around the camera, where ground fog lies."""
import numpy as np

from .atmosphere_haze import is_domain

LOW_GROUND_REACH = 3000.0
LOW_GROUND_SHARE = 0.05


def low_ground(scene, view_layer, bounds=None):
    """The low ground around the active camera: the 5th percentile of the heights of visible surfaces (land, water and
    everything on them) within 3 km of it, or of the scene without a camera. Returns (height, source)."""
    camera = scene.camera
    centre = np.array(camera.matrix_world.translation)[:2] if camera is not None else None
    heights = []
    for obj in scene.objects:
        if obj.type != "MESH" or is_domain(obj) or not obj.visible_get(view_layer=view_layer) or len(obj.data.vertices) == 0:
            continue
        local = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
        obj.data.vertices.foreach_get("co", local)
        matrix = np.array(obj.matrix_world, dtype=np.float64)
        world = local.reshape(-1, 3).astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
        if centre is not None:
            world = world[np.hypot(world[:, 0] - centre[0], world[:, 1] - centre[1]) <= LOW_GROUND_REACH]
        if bounds is not None:
            inside = np.all((world >= np.asarray(bounds["min"])) & (world <= np.asarray(bounds["max"])), axis=1)
            world = world[inside]
        if len(world):
            heights.append(world[:, 2])
    if not heights:
        return 0.0, "no ground found: 0"
    found = float(np.quantile(np.concatenate(heights), LOW_GROUND_SHARE))
    where = "within 3 km of the camera" if centre is not None else "in the scene"
    return round(found, 4), f"low ground {where}: the 5th percentile of surface heights"
