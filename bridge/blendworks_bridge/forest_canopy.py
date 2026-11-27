"""The canopy surface of distant forest: past the cards the land itself rises by the canopy height times the forest
share, and its material takes the crowns' colour there."""
import numpy

from . import forest_cards
from .land_field import smoothstep
from .land_material import FOREST_ATTRIBUTE
from .liquid_world import write_point_attribute
from .util import rounded

LIFT_ATTRIBUTE = "dl_canopy_lift"


def canopy_surface(land, points, eye, share, far, band, height, atlases, gain, crown):
    """Raise the land into a canopy where cards give way to it, and colour it as the crowns."""
    mesh = land.data
    previous = numpy.zeros(len(mesh.vertices), dtype=numpy.float32)
    if mesh.attributes.get(LIFT_ATTRIBUTE) is not None:
        mesh.attributes[LIFT_ATTRIBUTE].data.foreach_get("value", previous)
    distance = numpy.linalg.norm(points - eye, axis=1)
    weight = share * smoothstep(far * (1.0 - band), far * (1.0 + band), distance)
    lift = (height * weight).astype(numpy.float32)
    local = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
    mesh.vertices.foreach_get("co", local)
    local = local.reshape(-1, 3)
    local[:, 2] += lift - previous
    mesh.vertices.foreach_set("co", local.ravel())
    write_point_attribute(mesh, LIFT_ATTRIBUTE, lift)
    write_point_attribute(mesh, FOREST_ATTRIBUTE, weight)
    mesh.update()
    colour = crown_colour(atlases) * numpy.asarray(gain)
    forest_cards.add_canopy(land.data.materials[0], colour.tolist(), crown)
    return {"height": rounded(height, 3), "colour": [rounded(float(v), 5) for v in colour], "vertices": int((weight > 0.01).sum()),
            "starts_at": rounded(far * (1.0 - band), 3)}


def crown_colour(atlases):
    total, weight = numpy.zeros(3), 0.0
    for entry in atlases:
        alpha = entry["alpha"]
        total += (entry["colour"] * alpha[..., None]).sum(axis=(0, 1))
        weight += float(alpha.sum())
    return total / max(weight, 1e-9)
