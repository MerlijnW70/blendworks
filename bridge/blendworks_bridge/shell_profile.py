"""Shell generating curve profiles."""

import math

from .errors import bad_args
from .outlines import counter_clockwise, drop_repeats, signed_area

SHAPES = ("circle", "ellipse", "points")


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


class Profile:
    def __init__(self, points):
        u_min = min(u for u, _ in points)
        v_mid = (min(v for _, v in points) + max(v for _, v in points)) / 2.0
        self.points = [(u - u_min, v - v_mid) for u, v in points]
        self.width = max(u for u, _ in self.points)
        self.height = max(v for _, v in self.points) - min(v for _, v in self.points)
        self.count = len(self.points)
        self.normals = self.outward_normals()
        self.fractions = self.arc_fractions()

    def outward_normals(self):
        count = len(self.points)
        edges = []
        for index in range(count):
            (x0, y0), (x1, y1) = self.points[index], self.points[(index + 1) % count]
            length = math.hypot(x1 - x0, y1 - y0)
            edges.append(((y1 - y0) / length, -(x1 - x0) / length))
        normals = []
        for index in range(count):
            nx = edges[index - 1][0] + edges[index][0]
            ny = edges[index - 1][1] + edges[index][1]
            length = math.hypot(nx, ny)
            normals.append((nx / length, ny / length) if length > 1e-12 else edges[index])
        return normals

    def arc_fractions(self):
        count = len(self.points)
        cumulative = [0.0]
        for index in range(count):
            cumulative.append(cumulative[-1] + math.dist(self.points[index], self.points[(index + 1) % count]))
        return [value / cumulative[-1] for value in cumulative[:-1]]


def generating_curve(args):
    kind = args["profile"]
    stray = [key for key in ("aspect", "points", "profile_segments") if key in args and not applies(kind, key)]
    if stray:
        raise bad_args(f"{', '.join(stray)} does not apply to the {kind} profile")
    if kind == "points":
        if "points" not in args:
            raise bad_args("the points profile needs points")
        points = drop_repeats(args["points"], "the profile")
        if abs(signed_area(points)) < 1e-14:
            raise bad_args("the profile encloses no area")
        return counter_clockwise(points), True
    segments = args.get("profile_segments", 24)
    if segments % 4:
        raise bad_args("profile_segments must be a multiple of 4 so the profile has points on both axes")
    aspect = 1.0 if kind == "circle" else args.get("aspect", 0.6)
    return even_ellipse(0.5, 0.5 * aspect, segments), False


def even_ellipse(half_width, half_height, segments):
    fine = 8 * segments * 16
    outline = [(half_width * math.cos(math.tau * i / fine), half_height * math.sin(math.tau * i / fine)) for i in range(fine + 1)]
    cumulative = [0.0]
    for index in range(fine):
        cumulative.append(cumulative[-1] + math.dist(outline[index], outline[index + 1]))
    points, cursor = [], 0
    for step in range(segments):
        wanted = cumulative[-1] * step / segments
        while cumulative[cursor + 1] < wanted:
            cursor += 1
        along = (wanted - cumulative[cursor]) / (cumulative[cursor + 1] - cumulative[cursor])
        points.append(tuple(a + (b - a) * along for a, b in zip(outline[cursor], outline[cursor + 1])))
    return points


def applies(kind, key):
    return {"aspect": kind == "ellipse", "points": kind == "points", "profile_segments": kind != "points"}[key]


def normalised_profile(args):
    points, own_scale = generating_curve(args)
    extent = max(max(u for u, _ in points) - min(u for u, _ in points), max(v for _, v in points) - min(v for _, v in points))
    size = args["size"] if "size" in args else (extent if own_scale else 0.1)
    return Profile([(u / extent, v / extent) for u, v in points]), size
