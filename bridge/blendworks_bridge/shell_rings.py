"""Shell spiral rings."""

import math

from mathutils import Vector

from .shell_profile import smoothstep

TAIL_TURNS = 0.5


class Spiral:
    def __init__(self, profile, size, growth, distance, drop, turns, steps, ribs, ridges, lip):
        self.profile = profile
        self.size = size
        self.growth = growth
        self.turns = turns
        self.count = max(1, round(turns * steps))
        self.dt = turns / self.count
        self.tail = max(2, round(steps * TAIL_TURNS))
        self.inner = distance * profile.width / (1.0 - distance)
        centre = self.inner + profile.width / 2.0
        self.drop_rate = drop * size * growth ** (-turns) * centre / (growth - 1.0)
        self.ribs = ribs
        self.ridges = ridges
        self.lip = lip
        self.ridge_pattern = [0.5 - 0.5 * math.cos(math.tau * ridges["count"] * f) for f in profile.fractions] if ridges else None

    def times(self):
        return [(index - self.tail) * self.dt for index in range(self.tail + self.count + 1)]

    def scale(self, t):
        return self.size * self.growth ** (t - self.turns)

    def ease(self, t):
        return smoothstep((t + self.tail * self.dt) / (self.tail * self.dt))

    def lip_factor(self, t):
        return smoothstep((t - (self.turns - self.lip["length"])) / self.lip["length"]) if self.lip else 0.0

    def height(self, t):
        return -self.drop_rate * (self.growth ** t - 1.0)

    def centre_distance(self, t):
        return self.scale(t) * (self.inner + self.profile.width / 2.0)

    def coordinates(self, t):
        scale = self.scale(t)
        ease = self.ease(t)
        flare = 1.0 + (self.lip["flare"] * self.lip_factor(t) if self.lip else 0.0)
        rib = self.ribs["height"] * (0.5 - 0.5 * math.cos(math.tau * self.ribs["count"] * t)) if self.ribs else 0.0
        base = self.height(t)
        points = []
        for index, (u, v) in enumerate(self.profile.points):
            push = rib + (self.ridges["height"] * self.ridge_pattern[index] if self.ridges else 0.0)
            nx, ny = self.profile.normals[index]
            radial = max(scale * (self.inner * ease + flare * (u + nx * push * ease)), 0.0)
            points.append((radial, base + scale * flare * (v + ny * push * ease)))
        return points

    def ring(self, t):
        azimuth = -math.tau * t
        cos, sin = math.cos(azimuth), math.sin(azimuth)
        return [Vector((radial * cos, radial * sin, z)) for radial, z in self.coordinates(t)]
