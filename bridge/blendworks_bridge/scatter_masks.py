import numpy

from .errors import bad_args
from .noise_stack import stack_bounds, stack_field

MASKS = ("slope", "height", "vertex_group", "noise", "attribute")
MASK_PARAMETERS = {
    "slope": ("slope_range",),
    "height": ("height_range",),
    "vertex_group": ("vertex_group",),
    "noise": ("noise",),
    "attribute": ("attribute", "attribute_range"),
}


def chosen_masks(args):
    masks = list(dict.fromkeys(args.get("density_mask", [])))
    for mask, parameters in MASK_PARAMETERS.items():
        for parameter in parameters:
            if mask in masks and parameter not in args:
                raise bad_args(f"density_mask {mask} needs {parameter}")
            if mask not in masks and parameter in args:
                raise bad_args(f"{parameter} has no effect unless density_mask lists {mask}")
    return masks


def inside(values, bounds):
    return ((values >= bounds[0]) & (values <= bounds[1])).astype(float)


def ramp(values, low, high):
    if high <= low:
        return (values >= low).astype(float)
    return numpy.clip((values - low) / (high - low), 0.0, 1.0)


def slope_degrees(normals):
    return numpy.degrees(numpy.arccos(numpy.clip(normals[:, 2], -1.0, 1.0)))


def mask_values(surface, args, masks, triangle, weights, points):
    density = numpy.ones(len(triangle))
    if "slope" in masks:
        density *= inside(slope_degrees(surface.normals[triangle]), args["slope_range"])
    if "height" in masks:
        density *= inside(points[:, 2], args["height_range"])
    if "vertex_group" in masks:
        density *= numpy.clip(surface.interpolate(surface.weights, triangle, weights), 0.0, 1.0)
    if "attribute" in masks:
        low, high = args["attribute_range"]
        density *= ramp(surface.interpolate(surface.attribute, triangle, weights), low, high)
    if "noise" in masks:
        noise = args["noise"]
        lowest, highest = stack_bounds(noise)
        unit = (stack_field(points, noise) - lowest) / (highest - lowest)
        density *= numpy.clip((unit - noise["threshold"]) / noise["softness"] + 0.5, 0.0, 1.0)
    return density
