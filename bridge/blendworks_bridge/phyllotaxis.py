"""Phyllotaxis layout on a disc: sites, divergence and age curves."""

import math
import random
from dataclasses import dataclass

from mathutils import Matrix, Vector

from .errors import bad_args
from .kit_limits import MAX_INSTANCES
from .phyllotaxis_surface import rigid_world, surface_sites

GOLDEN_RATIO = (1.0 + math.sqrt(5.0)) / 2.0
GOLDEN_DEGREES = 360.0 * (1.0 - 1.0 / GOLDEN_RATIO)
DEFAULT_DIVERGENCE = 137.5
MODES = ("disc", "cylinder", "cone", "sphere", "surface")
CURVES = ("linear", "ease_in", "ease_out", "smooth")
MODE_FIELDS = {
    "disc": {"c"},
    "cylinder": {"radius", "height"},
    "cone": {"radius", "height", "c"},
    "sphere": {"radius", "polar_extent"},
    "surface": {"target"},
}
REQUIRED_FIELDS = {"disc": ("c",), "cylinder": ("radius", "height"), "cone": ("radius", "height"), "sphere": ("radius",), "surface": ("target",)}
MODE_ONLY_FIELDS = ("c", "radius", "height", "polar_extent", "target")


@dataclass(frozen=True)
class Site:
    azimuth: float
    r: float
    z: float
    tangent: tuple
    normal: tuple


@dataclass(frozen=True)
class Layout:
    placements: list
    sites: list
    summary: dict


def curve_value(curve, fraction):
    if curve == "linear":
        return fraction
    if curve == "ease_in":
        return fraction * fraction
    if curve == "ease_out":
        return 1.0 - (1.0 - fraction) ** 2
    return fraction * fraction * (3.0 - 2.0 * fraction)


def age_value(spec, fraction):
    return spec["from"] + (spec["to"] - spec["from"]) * curve_value(spec["curve"], fraction)


def divergence_degrees(spec):
    return GOLDEN_DEGREES if spec["golden"] else spec.get("divergence", DEFAULT_DIVERGENCE)


def check_fields(spec):
    mode = spec["mode"]
    for field in MODE_ONLY_FIELDS:
        if field in spec and field not in MODE_FIELDS[mode]:
            raise bad_args(f"{field} does not apply to phyllotaxis mode {mode}")
    for field in REQUIRED_FIELDS[mode]:
        if field not in spec:
            raise bad_args(f"phyllotaxis mode {mode} needs {field}")
    if spec["golden"] and "divergence" in spec:
        raise bad_args("give divergence or golden, not both")


def disc_sites(spec, indices, angle):
    return [Site(n * angle, spec["c"] * math.sqrt(n), 0.0, (1.0, 0.0), (0.0, 1.0)) for n in indices], math.pi * spec["c"] ** 2


def cylinder_sites(spec, indices, angle):
    count, first = spec["count"], spec["start"]
    sites = []
    for n in indices:
        fraction = (n - first) / (count - 1) if count > 1 else 0.0
        sites.append(Site(n * angle, spec["radius"], spec["height"] * fraction, (0.0, 1.0), (1.0, 0.0)))
    pitch = spec["height"] / (count - 1) if count > 1 else spec["height"]
    return sites, 2.0 * math.pi * spec["radius"] * pitch


def cone_sites(spec, indices, angle):
    radius, height = spec["radius"], spec["height"]
    slant = math.hypot(radius, height)
    c = spec.get("c", slant / math.sqrt(spec["start"] + spec["count"]))
    sites = []
    for n in indices:
        distance = c * math.sqrt(n)
        if distance > slant + 1e-9:
            raise bad_args(f"organ {n} lies {distance:.4f} m down the slope, past the base edge at {slant:.4f} m; lower c, count or start")
        share = distance / slant
        sites.append(Site(n * angle, radius * share, height * (1.0 - share), (radius / slant, -height / slant), (height / slant, radius / slant)))
    return sites, math.pi * radius / slant * c * c


def sphere_sites(spec, indices, angle):
    radius, count = spec["radius"], spec["count"]
    drop = 1.0 - math.cos(math.radians(spec.get("polar_extent", 180.0)))
    sites = []
    for n in indices:
        z = 1.0 - drop * (n - spec["start"] + 0.5) / count
        sine = math.sqrt(max(0.0, 1.0 - z * z))
        sites.append(Site(n * angle, radius * sine, radius * z, (z, -sine), (sine, z)))
    return sites, 2.0 * math.pi * radius * radius * drop / count


def mode_sites(spec, indices, angle, target):
    mode = spec["mode"]
    if mode == "surface":
        return surface_sites(Site, target, spec["count"], [n * angle for n in indices])
    builder = {"disc": disc_sites, "cylinder": cylinder_sites, "cone": cone_sites, "sphere": sphere_sites}[mode]
    return builder(spec, indices, angle)


def site_frame(site, align):
    radial = Vector((math.cos(site.azimuth), math.sin(site.azimuth), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    position = radial * site.r + up * site.z
    if align == "radial":
        x, z = radial, up
    else:
        x = radial * site.tangent[0] + up * site.tangent[1]
        z = radial * site.normal[0] + up * site.normal[1]
    y = z.cross(x)
    matrix = Matrix.Identity(4)
    for row in range(3):
        matrix[row][0], matrix[row][1], matrix[row][2], matrix[row][3] = x[row], y[row], z[row], position[row]
    return matrix


def jittered(spec, matrix, rng, spacing):
    jitter = spec["jitter"]
    along, around, yaw, grow = (rng.uniform(-1.0, 1.0) for _ in range(4))
    shifted = matrix.copy()
    shifted.translation = matrix.translation + matrix.to_3x3() @ Vector((along, around, 0.0)) * (jitter["amount"] * spacing)
    return shifted, math.radians(jitter["rotation"] * yaw), 1.0 + jitter["scale"] * grow


def organ_matrix(matrix, tilt_degrees, yaw, factor):
    return matrix @ Matrix.Rotation(-math.radians(tilt_degrees), 4, "Y") @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Scale(factor, 4)


def phyllotaxis_layout(spec, align, target=None):
    check_fields(spec)
    if align == "none" and "tilt_by_age" in spec:
        raise bad_args("tilt_by_age needs align frame or radial")
    count = spec["count"]
    if count > MAX_INSTANCES:
        raise bad_args(f"{count} instances; the cap is {MAX_INSTANCES}")
    degrees = divergence_degrees(spec)
    sites, area = mode_sites(spec, [spec["start"] + index for index in range(count)], math.radians(degrees), target)
    rng = random.Random(spec["jitter"]["seed"]) if "jitter" in spec else None
    spacing = math.sqrt(area)
    world = rigid_world(target) if spec["mode"] == "surface" else Matrix.Identity(4)
    placements = []
    for index, site in enumerate(sites):
        age = index / (count - 1) if count > 1 else 0.0
        matrix = site_frame(site, "frame" if align == "none" else align)
        yaw, factor = 0.0, 1.0
        if rng is not None:
            matrix, yaw, factor = jittered(spec, matrix, rng, spacing)
        if "scale_by_age" in spec:
            factor *= age_value(spec["scale_by_age"], age)
        tilt = age_value(spec["tilt_by_age"], age) if "tilt_by_age" in spec else 0.0
        organ = world @ organ_matrix(matrix, tilt, yaw, factor)
        placements.append(Matrix.Translation(organ.translation) @ Matrix.Scale(factor, 4) if align == "none" else organ)
    summary = {"divergence": round(degrees, 9), "area_per_organ": area, "first_index": spec["start"]}
    return Layout(placements, sites, summary)
