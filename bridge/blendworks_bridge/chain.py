"""Geometry of roller chain parts: plates, rollers, pins and the wheel path."""

import math

from mathutils import Matrix, Vector

from .errors import bad_args
from .extrusion import extrusion_data
from .meshdata import MeshData
from .outlines import circle_points
from .paths import clean_path, path_length, point_along
from .revolve import lathe_data
from .uvlayout import pack_islands

ARC_SEGMENTS = 6
ROLLER_SEGMENTS = 16
PIN_SEGMENTS = 10
HOLE_SEGMENTS = 12


class ChainSizes:
    def __init__(self, pitch, args):
        self.pitch = pitch
        self.roller = args.get("roller_diameter", 0.625 * pitch)
        self.pin = args.get("pin_diameter", 0.31 * pitch)
        self.inner_width = args.get("inner_width", 0.625 * pitch)
        self.plate = args.get("plate_thickness", 0.1 * pitch)
        self.plate_radius = args.get("plate_height", 0.8 * pitch) / 2.0
        self.gap = 0.02 * pitch
        if self.pin >= self.roller * 0.9:
            raise bad_args("pin_diameter must be well below roller_diameter")
        if self.plate_radius * 2 <= self.roller * 0.8:
            raise bad_args("plate_height must exceed the roller diameter")
        if self.pin / 2.0 >= self.plate_radius * 0.8:
            raise bad_args("pin_diameter leaves no plate around the pin hole")

    def outer_face(self):
        return self.inner_width / 2.0 + self.plate + self.gap

    def pin_half_length(self):
        return self.outer_face() + self.plate + self.pin * 0.2


def stadium(length, radius):
    points = []
    for centre, start in ((length / 2.0, -math.pi / 2), (-length / 2.0, math.pi / 2)):
        for step in range(ARC_SEGMENTS + 1):
            angle = start + math.pi * step / ARC_SEGMENTS
            points.append((centre + radius * math.cos(angle), radius * math.sin(angle)))
    return points


def plate_data(length, sizes, z_low):
    holes = [[(x + length / 2.0 * side, y) for x, y in circle_points(sizes.pin / 2.0, HOLE_SEGMENTS)] for side in (-1, 1)]
    data = extrusion_data(stadium(length, sizes.plate_radius), holes, sizes.plate, 0.0, 1, False)
    data.transform(Matrix.Translation((0.0, 0.0, z_low)))
    pack_islands(data)
    return data


def roller_data(sizes):
    half = sizes.inner_width / 2.0
    r_out, r_in = sizes.roller / 2.0, sizes.pin / 2.0
    data = lathe_data([(r_in, -half), (r_out, -half), (r_out, half), (r_in, half)], "z", ROLLER_SEGMENTS, 360.0, True, True, True)
    pack_islands(data)
    return data


def pin_data(sizes):
    half, radius = sizes.pin_half_length(), sizes.pin / 2.0
    cut = radius * 0.2
    profile = [(0.0, -half), (radius - cut, -half), (radius, -half + cut), (radius, half - cut), (radius - cut, half), (0.0, half)]
    data = lathe_data(profile, "z", PIN_SEGMENTS, 360.0, True, True, False)
    pack_islands(data)
    return data


def hull(points):
    unique = sorted(set(points))

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for point in unique:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(unique):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def wheel_path(wheels, normal):
    reference = Vector((1.0, 0.0, 0.0)) if abs(normal.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    first = (reference - normal * reference.dot(normal)).normalized()
    second = normal.cross(first)
    heights = [Vector(wheel["centre"]).dot(normal) for wheel in wheels]
    if max(heights) - min(heights) > 1e-6:
        raise bad_args("all wheel centres must lie in one plane perpendicular to plane_normal")
    samples = []
    for wheel in wheels:
        centre = Vector(wheel["centre"])
        u, v = centre.dot(first), centre.dot(second)
        for step in range(96):
            angle = math.tau * step / 96
            samples.append((u + wheel["radius"] * math.cos(angle), v + wheel["radius"] * math.sin(angle)))
    outline = hull(samples)
    return [first * u + second * v + normal * heights[0] for u, v in outline]


class ChainRoute:
    """The links a path holds at a pitch, counted from its length alone, before any pin is placed."""

    def __init__(self, points, closed, pitch):
        self.points = clean_path(points, closed)
        self.closed = closed
        self.pitch = pitch
        self.total = path_length(self.points, closed)
        if closed:
            self.links = max(4, 2 * round(self.total / pitch / 2.0))
            self.step = self.total / self.links
            self.count = self.links
        else:
            self.links = int(self.total / pitch + 1e-9)
            if self.links < 1:
                raise bad_args("the path is shorter than one chain pitch")
            self.step = pitch
            self.count = self.links + 1

    def check_links(self, cap):
        """Exact: links is the count the pins are placed from, taken from the path length alone."""
        if self.links > cap:
            raise bad_args(f"pitch {self.pitch:g} m along this {self.total:g} m path makes {self.links} links; the "
                           f"{cap.key} limit is {cap.plain()} ({cap.reason}) Raise pitch to at least "
                           f"{self.total / cap.plain():.6g} m or shorten the path.")

    def pins(self):
        return [point_along(self.points, self.closed, self.step * index)[0] for index in range(self.count)]


def element_matrix(a, b, normal):
    x = (b - a).normalized()
    z = (normal - x * normal.dot(x))
    if z.length < 1e-9:
        raise bad_args("the chain runs along plane_normal; choose a normal perpendicular to the chain")
    z.normalize()
    y = z.cross(x)
    matrix = Matrix.Identity(4)
    centre = (a + b) / 2.0
    for row in range(3):
        matrix[row][0], matrix[row][1], matrix[row][2], matrix[row][3] = x[row], y[row], z[row], centre[row]
    return matrix


def chain_data(pins, closed, normal, sizes):
    data = MeshData()
    templates = {}
    roller = roller_data(sizes)
    pin = pin_data(sizes)
    count = len(pins)
    elements = count if closed else count - 1
    for index in range(elements):
        a, b = pins[index], pins[(index + 1) % count]
        matrix = element_matrix(a, b, normal)
        length = (b - a).length
        key = round(length, 7)
        inner = index % 2 == 0
        if (key, inner) not in templates:
            low = sizes.inner_width / 2.0 if inner else sizes.outer_face()
            plate = plate_data(length, sizes, low)
            mirrored = plate.copy().transform(Matrix.Scale(-1.0, 4, Vector((0.0, 0.0, 1.0))))
            templates[(key, inner)] = (plate, mirrored)
        for part in templates[(key, inner)]:
            data.append(part, matrix)
    for index, position in enumerate(pins):
        previous = pins[index - 1] if index > 0 or closed else pins[index + 1]
        following = pins[(index + 1) % count] if index < count - 1 or closed else pins[index - 1]
        matrix = element_matrix(previous, following, normal)
        matrix.translation = position
        data.append(roller, matrix)
        data.append(pin, matrix)
    return data
