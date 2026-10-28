import math

from mathutils import Matrix

from .errors import bad_args


def uniform_scale(obj):
    scale = obj.matrix_world.to_scale()
    if max(scale) - min(scale) > 1e-6 * max(abs(max(scale)), 1e-12) or min(scale) <= 0:
        raise bad_args(f"{obj.name} has a non-uniform or mirrored scale; apply its scale first")
    return scale[0]


def rigid_world(obj):
    rotation = obj.matrix_world.to_quaternion().to_matrix().to_4x4()
    return Matrix.Translation(obj.matrix_world.translation) @ rotation


def revolution_profile(obj, scale):
    heights = [vertex.co.z * scale for vertex in obj.data.vertices]
    if not heights:
        raise bad_args(f"{obj.name} has no vertices")
    tolerance = 1e-6 * max(1.0, max(heights) - min(heights))
    levels = {}
    for vertex in obj.data.vertices:
        height = vertex.co.z * scale
        radius = math.hypot(vertex.co.x, vertex.co.y) * scale
        key = round(height / tolerance)
        if key not in levels or radius > levels[key][0]:
            levels[key] = (radius, height)
    ordered = sorted(levels.values(), key=lambda level: -level[1])
    if len(ordered) < 2:
        raise bad_args(f"{obj.name} needs vertices at two or more heights to be a surface of revolution about its Z axis")
    return ordered


def point_at_area(profile, areas, wanted):
    index = 1
    while index < len(areas) - 1 and areas[index] < wanted:
        index += 1
    (r0, z0), (r1, z1) = profile[index - 1], profile[index]
    slant = math.hypot(r1 - r0, z1 - z0)
    rest = wanted - areas[index - 1]
    if abs(r1 - r0) < 1e-12:
        share = rest / (2.0 * math.pi * r0 * slant) if r0 > 0 else 0.0
    else:
        share = (-r0 + math.sqrt(max(0.0, r0 * r0 + (r1 - r0) * rest / (math.pi * slant)))) / (r1 - r0)
    share = min(1.0, max(0.0, share))
    return r0 + (r1 - r0) * share, z0 + (z1 - z0) * share, ((r1 - r0) / slant, (z1 - z0) / slant)


def surface_sites(make_site, target, count, azimuths):
    profile = revolution_profile(target, uniform_scale(target))
    areas = [0.0]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        areas.append(areas[-1] + math.pi * (r0 + r1) * math.hypot(r1 - r0, z1 - z0))
    total = areas[-1]
    if total <= 0:
        raise bad_args(f"{target.name} has no surface area")
    sites = []
    for index, azimuth in enumerate(azimuths):
        radius, height, tangent = point_at_area(profile, areas, total * (index + 0.5) / count)
        sites.append(make_site(azimuth, radius, height, tangent, (-tangent[1], tangent[0])))
    return sites, total / count
