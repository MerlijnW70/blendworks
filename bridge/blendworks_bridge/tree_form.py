"""Tree form: response to wind, gnarl and per-order settings."""

import math

import numpy

from .tree_colonize import SHOOT
from .tree_strands import Sway
from .tree_vectors import IDENTITY, add, axis_angle, cross, mat_mul, mat_vec, norm, perpendicular, scaled, towards

FORM_FIELDS = ("gravitropism", "phototropism", "stiffness", "gnarl", "twist", "kink_probability", "kink_angle", "wind", "sway", "hem")
DOWN = (0.0, 0.0, -1.0)
RESPONSE_DEFAULTS = {"strength": 0.0, "by_order": [1.0], "thinness": 1.0}
GNARL_DEFAULTS = {"amplitude": 0.0, "wavelength": 2.0, "radius_power": 1.0, "by_order": [1.0]}
WIND_DEFAULTS = {"vector": [0.0, 0.0, 0.0], "profile": 0.3, "thinness": 1.0}
DEFAULT_KINK_ANGLE = 30.0
GNARL_OCTAVES = 3
SAG_SHARE = 4.0


def form_active(settings):
    return any(name in settings for name in FORM_FIELDS)


def per_order(values, order):
    return float(values[min(int(order), len(values) - 1)])


class Response:
    def __init__(self, given, defaults, target=None):
        values = {**defaults, **(given or {})}
        self.strength = float(values.get("strength", 0.0))
        self.by_order = values.get("by_order", [1.0])
        self.thinness = float(values.get("thinness", 1.0))
        self.target = target

    def weight(self, order, radius, tip_radius):
        return self.strength * per_order(self.by_order, order) * (tip_radius / radius) ** self.thinness


class Wind:
    def __init__(self, given, height):
        values = {**WIND_DEFAULTS, **(given or {})}
        vector = tuple(float(value) for value in values["vector"])
        self.strength = norm(vector)
        self.target = scaled(vector, 1.0 / self.strength) if self.strength > 0.0 else None
        self.profile = float(values["profile"])
        self.thinness = float(values["thinness"])
        self.height = float(height)

    def weight(self, height, radius, tip_radius):
        share = min(max(height / self.height, 0.0), 1.0)
        return self.strength * share**self.profile * (tip_radius / radius) ** self.thinness


class Gnarl:
    def __init__(self, given, seed):
        values = {**GNARL_DEFAULTS, **(given or {})}
        self.amplitude = float(values["amplitude"])
        self.wavelength = float(values["wavelength"])
        self.radius_power = float(values["radius_power"])
        self.by_order = values["by_order"]
        rng = numpy.random.default_rng([seed, 4])
        directions = rng.normal(size=(3, GNARL_OCTAVES, 3))
        self.directions = directions / numpy.linalg.norm(directions, axis=2, keepdims=True)
        self.phases = rng.random((3, GNARL_OCTAVES)) * 2.0 * math.pi
        weights = 0.5 ** numpy.arange(GNARL_OCTAVES)
        self.weights = weights / weights.sum()
        self.frequencies = 2.0 * math.pi * 2.0 ** numpy.arange(GNARL_OCTAVES) / self.wavelength

    def field(self, points):
        values = numpy.zeros((len(points), 3))
        for component in range(3):
            waves = numpy.sin(points @ self.directions[component].T * self.frequencies + self.phases[component])
            values[:, component] = waves @ self.weights
        return values

    def offsets(self, positions, parents, kinds, orders, radii):
        count = len(parents)
        local = numpy.zeros((count, 3))
        if self.amplitude <= 0.0 or count < 2:
            return local
        tangents = positions[1:] - positions[parents[1:]]
        lengths = numpy.linalg.norm(tangents, axis=1, keepdims=True)
        tangents = numpy.divide(tangents, lengths, out=numpy.zeros_like(tangents), where=lengths > 1e-12)
        noise = self.field(positions[1:])
        across = noise - numpy.einsum("ij,ij->i", noise, tangents)[:, None] * tangents
        size = numpy.linalg.norm(across, axis=1, keepdims=True)
        across /= numpy.maximum(size, 1.0)
        scale = numpy.array([per_order(self.by_order, order) for order in orders[1:]]) * (radii[1:] / radii[0]) ** self.radius_power
        local[1:] = self.amplitude * scale[:, None] * across
        local[1:][kinds[1:] != SHOOT] = 0.0
        return local


class Form:
    def __init__(self, settings, seed, height):
        self.tip_radius = float(settings["tip_radius"])
        self.gravity = Response(settings.get("gravitropism"), RESPONSE_DEFAULTS, DOWN)
        light = settings.get("phototropism") or {}
        target = tuple(float(value) for value in light.get("direction", [0.0, 0.0, 1.0]))
        self.light = Response(light, RESPONSE_DEFAULTS, scaled(target, 1.0 / max(norm(target), 1e-12)))
        self.wind = Wind(settings.get("wind"), height)
        self.stiffness = settings.get("stiffness")
        self.twist = math.radians(float(settings.get("twist", 0.0)))
        self.kink_probability = float(settings.get("kink_probability", 0.0))
        self.kink_angle = math.radians(float(settings.get("kink_angle", DEFAULT_KINK_ANGLE)))
        self.gnarl = Gnarl(settings.get("gnarl"), seed)
        self.sway = Sway(settings.get("sway"), seed)
        self.seed = seed

    def kinks(self, parents, kinds):
        rng = numpy.random.default_rng([self.seed, 3])
        draws = rng.random(len(parents))
        azimuths = rng.random(len(parents)) * 2.0 * math.pi
        chosen = (draws < self.kink_probability) & (kinds == SHOOT) & (parents > 0)
        chosen[0] = False
        return chosen, azimuths

    def pulls(self, order, radius, height):
        found = []
        for response in (self.gravity, self.light):
            if response.strength > 0.0:
                found.append((response.target, response.weight(order, radius, self.tip_radius)))
        if self.wind.target is not None:
            found.append((self.wind.target, self.wind.weight(height, radius, self.tip_radius)))
        return found

    def rebuild(self, positions, parents, kinds, orders, radii, kinked, azimuths, sag=None):
        count = len(parents)
        old = [tuple(float(value) for value in row) for row in positions]
        new = [old[0]] + [None] * (count - 1)
        frames = [IDENTITY] * count
        for node in range(1, count):
            parent = int(parents[node])
            offset = tuple(a - b for a, b in zip(old[node], old[parent]))
            if kinds[node] != SHOOT:
                frames[node] = frames[parent]
                new[node] = add(new[parent], mat_vec(frames[parent], offset))
                continue
            length = norm(offset)
            if length < 1e-12:
                frames[node] = frames[parent]
                new[node] = new[parent]
                continue
            heading = mat_vec(frames[parent], scaled(offset, 1.0 / length))
            turn = IDENTITY
            if kinked[node]:
                rotation = axis_angle(perpendicular(heading, azimuths[node]), self.kink_angle)
                heading = mat_vec(rotation, heading)
                turn = rotation
            for target, rate in self.pulls(orders[node], radii[node], new[parent][2]) + self.sway.pull(node):
                angle = rate * length * norm(cross(heading, target))
                rotation = towards(heading, target, angle)
                heading = mat_vec(rotation, heading)
                turn = mat_mul(rotation, turn)
            if sag is not None and sag[node] > 0.0:
                rotation = towards(heading, DOWN, sag[node] * length)
                heading = mat_vec(rotation, heading)
                turn = mat_mul(rotation, turn)
            if self.twist and orders[node] == 0:
                turn = mat_mul(axis_angle(heading, self.twist * length), turn)
            frames[node] = mat_mul(turn, frames[parent])
            new[node] = add(new[parent], scaled(heading, length))
        return numpy.array(new)

    def sag_curvature(self, positions, parents, kinds, radii):
        count = len(parents)
        segments = positions[1:] - positions[parents[1:]]
        mass = numpy.zeros(count)
        mass[1:] = radii[1:] ** 2 * numpy.linalg.norm(segments, axis=1)
        moment = numpy.zeros((count, 3))
        moment[1:] = mass[1:, None] * 0.5 * (positions[1:] + positions[parents[1:]])
        for node in range(count - 1, 0, -1):
            parent = parents[node]
            if parent > 0 and kinds[parent] == SHOOT:
                mass[parent] += mass[node]
                moment[parent] += moment[node]
        curvature = numpy.zeros(count)
        loaded = (mass > 0.0) & (kinds == SHOOT)
        loaded[0] = False
        centre = numpy.zeros((count, 3))
        centre[loaded] = moment[loaded] / mass[loaded, None]
        arm = numpy.hypot(*(centre[loaded] - positions[parents[loaded]])[:, :2].T)
        curvature[loaded] = SAG_SHARE * mass[loaded] * arm / (float(self.stiffness) * radii[loaded] ** 4)
        return curvature

    def apply(self, positions, parents, kinds, orders, radii):
        kinked, azimuths = self.kinks(parents, kinds)
        self.sway.prepare(parents, orders, kinds)
        shaped = self.rebuild(positions, parents, kinds, orders, radii, kinked, azimuths)
        sag = None
        if self.stiffness is not None:
            sag = self.sag_curvature(shaped, parents, kinds, radii)
            shaped = self.rebuild(positions, parents, kinds, orders, radii, kinked, azimuths, sag)
        local = self.gnarl.offsets(shaped, parents, kinds, orders, radii)
        offsets = numpy.zeros_like(local)
        inherited = numpy.zeros_like(local)
        for node in range(1, len(parents)):
            parent = parents[node]
            inherited[node] = offsets[parent] if orders[node] != orders[parent] or kinds[node] != kinds[parent] else inherited[parent]
            offsets[node] = inherited[node] + local[node]
        shaped = shaped + offsets
        report = {"kinks": int(kinked.sum()), "largest_gnarl": round(float(numpy.linalg.norm(local, axis=1).max()), 6)}
        if sag is not None:
            report["largest_sag_curvature"] = round(float(sag.max()), 6)
        return shaped, report


def above_ground(positions, parents, kinds):
    keep = numpy.ones(len(parents), dtype=bool)
    base = positions[0][2]
    for node in range(1, len(parents)):
        keep[node] = keep[parents[node]] and not (kinds[node] == SHOOT and positions[node][2] <= base)
    return keep


def reindex(keep, parents):
    new_index = numpy.cumsum(keep) - 1
    kept = numpy.flatnonzero(keep)
    remapped = parents[kept].copy()
    remapped[1:] = new_index[remapped[1:]]
    return kept, remapped
