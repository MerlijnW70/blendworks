"""Render settings for liquid scenes."""

from .liquid_world import liquid_objects

RAISED = {"transmission_bounces": 16, "transparent_max_bounces": 32, "max_bounces": 16, "glossy_bounces": 8}
FILTER_GLOSSY = 1.0
CLAMP_INDIRECT = 10.0


def configure(scope, scene):
    """Render settings refractive liquids need: enough transmission bounces to pass glass and liquid, and no caustic paths,
    which Cycles can only find by chance and which otherwise turn into fireflies; light still reaches under water through
    the liquids' clear shadow rays."""
    liquids = liquid_objects(scene)
    if not liquids:
        return None
    cycles = scene.cycles
    scope.keep(cycles, "caustics_reflective", "caustics_refractive", "blur_glossy", "sample_clamp_indirect", *RAISED)
    cycles.caustics_reflective = False
    cycles.caustics_refractive = False
    cycles.blur_glossy = max(cycles.blur_glossy, FILTER_GLOSSY)
    if cycles.sample_clamp_indirect <= 0.0 or cycles.sample_clamp_indirect > CLAMP_INDIRECT:
        cycles.sample_clamp_indirect = CLAMP_INDIRECT
    for name, value in RAISED.items():
        setattr(cycles, name, max(getattr(cycles, name), value))
    return {
        "objects": sorted(obj.name for obj in liquids),
        "caustics": False,
        "filter_glossy": round(cycles.blur_glossy, 6),
        "clamp_indirect": round(cycles.sample_clamp_indirect, 6),
        "bounces": {name: getattr(cycles, name) for name in RAISED},
    }
