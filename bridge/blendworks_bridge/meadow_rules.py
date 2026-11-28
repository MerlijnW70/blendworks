"""Cover responses to the meadow fields.

How a ground-cover population follows the meadow fields: responses that thin it, make it taller or shorter, turn it
from green to straw and pick riper elements, each a linear ramp over one field; and the drifts flowers grow in."""
import numpy

from .limits import ELLENBERG_HIGHEST, ELLENBERG_LOWEST, FRACTION, MAX_LENGTH, MOST_RESPONSES, SMALLEST_COVER_PATCH, TALLEST_RESPONSE
from .meadow_fields import FIELDS, PATH_REACH, TREAD_HALF_WIDTH, VERGE_HALF_WIDTH, smoothstep
from .meadow_paths import path_distance
from .schema import array, described, number, obj, string

EFFECTS = ("density", "height", "dryness", "maturity")
SHORTEST_FACTOR = 0.05
INSTANCE_JITTER = 0.15


def pair(description, low, high):
    return array({"type": "number", "minimum": low, "maximum": high}, description, 2, 2)


RESPONSE = described(
    obj(
        {
            "field": string("Meadow field the response reads: moisture, soil (depth), disturbance, shade or grazing, each 0 to 1.", list(FIELDS)),
            "affects": string("density multiplies the density (at most 1, so it only thins); height scales the elements' height; dryness adds to the share turned from green to the dry colour; maturity adds to the share of riper elements with seed heads and dead tips.", list(EFFECTS)),
            "range": pair("Field values where the response starts and ends; outside them it holds its end value.", 0.0, FRACTION),
            "values": pair("Response at the start and at the end of range: a factor for density (0 to 1) and height, a share for dryness and maturity (-1 to 1).", -FRACTION, TALLEST_RESPONSE),
        },
        ["field", "affects", "range", "values"],
    ),
    "A linear response of the population to one meadow field.",
)

DRIFT = described(
    obj(
        {
            "moisture": number("Ellenberg moisture value F of the species, 1 (very dry) to 12 (under water): drifts of it form where the meadow's moisture, as F 3 to 9, is near this.", ELLENBERG_LOWEST, ELLENBERG_HIGHEST),
            "radius": pair("Smallest and largest drift radius in metres.", SMALLEST_COVER_PATCH, MAX_LENGTH),
            "share": number("How often this species takes a drift against the other drifting species, where moisture suits them equally.", 0.0, MAX_LENGTH, 1.0),
        },
        ["moisture", "radius"],
    ),
    "Grow this flower in drifts of one species: discs of radius whose species follows the moisture; a few strays grow outside.",
)

FIELD_PROPERTIES = {
    "responses": array(RESPONSE, "Responses to the meadow fields; ground_cover then computes the fields (or reads them from the target). An empty list drops a preset population's responses.", 0, MOST_RESPONSES),
    "drift": DRIFT,
}


def check_responses(population, bad_args):
    for response in population.get("responses", []):
        low, high = response["values"]
        if response["affects"] == "density" and not (0.0 <= low <= FRACTION and 0.0 <= high <= FRACTION):
            raise bad_args(f"population {population['name']}: a density response thins, so its values lie between 0 and 1")
        if response["affects"] == "height" and min(low, high) < SHORTEST_FACTOR:
            raise bad_args(f"population {population['name']}: a height response scales by at least {SHORTEST_FACTOR}")
        if response["affects"] in ("dryness", "maturity") and max(low, high) > 1.0:
            raise bad_args(f"population {population['name']}: a {response['affects']} response adds a share between -1 and 1")
        if response["range"][0] == response["range"][1]:
            raise bad_args(f"population {population['name']}: a response range needs two different field values")


def uses_fields(population):
    return bool(population.get("responses")) or "drift" in population


def ramp(values, response):
    (start, end), (low, high) = response["range"], response["values"]
    t = numpy.clip((values - start) / (end - start), 0.0, 1.0)
    return low + (high - low) * t


def effect(population, fields, name):
    """The combined response of one effect at the candidates: a product for density and height, a sum for the shares."""
    responses = [response for response in population.get("responses", []) if response["affects"] == name]
    count = len(next(iter(fields.values()))) if fields else 0
    if name in ("density", "height"):
        total = numpy.ones(count)
        for response in responses:
            total *= ramp(fields[response["field"]], response)
        return total
    total = numpy.zeros(count)
    for response in responses:
        total += ramp(fields[response["field"]], response)
    return total


def has_effect(population, name):
    return any(response["affects"] == name for response in population.get("responses", []))


class FieldSampler:
    """The meadow fields at points of the cover target: interpolated from its vertices, with the path tread measured
    exactly where the vertices say a path is near, since a tread is narrower than the vertex spacing."""

    def __init__(self, surface, values, lines):
        self.corners = {name: numpy.asarray(values[name], dtype=float)[surface.vertex_ids] for name in FIELDS}
        self.surface = surface
        self.lines = lines

    def triangle_bound(self, population):
        """Per triangle, the most the population's density responses allow anywhere on it: each ramp at whichever end of
        the triangle's field values it is largest, the tread able to raise disturbance to 1 where paths run."""
        bound = numpy.ones(len(self.surface.areas))
        for response in population.get("responses", []):
            if response["affects"] != "density":
                continue
            corners = self.corners[response["field"]]
            low, high = corners.min(axis=1), corners.max(axis=1)
            if response["field"] == "disturbance" and self.lines:
                high = numpy.where(high > 0.02, 1.0, high)
            bound *= response_bound(response, low, high)
        return numpy.clip(bound, 0.0, 1.0)

    def at(self, candidates):
        found = {name: self.surface.interpolate(corners, candidates.triangle, candidates.weights) for name, corners in self.corners.items()}
        if self.lines:
            near = numpy.nonzero(found["disturbance"] > 0.02)[0]
            if len(near):
                tread = path_distance(self.lines, candidates.points[near], PATH_REACH)
                worn = 1.0 - smoothstep(TREAD_HALF_WIDTH, VERGE_HALF_WIDTH, tread)
                found["disturbance"][near] = numpy.maximum(found["disturbance"][near], worn)
        return found


def response_bound(response, low, high):
    """The largest a linear ramp reaches for field values between low and high."""
    return numpy.maximum(ramp(low, response), ramp(high, response))


def instance_shares(population, fields, rng):
    """Per instance: the height factor, the dry share and the ripeness from the responses, with a little jitter."""
    count = len(fields["moisture"])
    height = effect(population, fields, "height")
    dryness = numpy.clip(effect(population, fields, "dryness") + rng.normal(0.0, INSTANCE_JITTER, count), 0.0, 1.0)
    maturity = numpy.clip(effect(population, fields, "maturity") + rng.uniform(-1.0, 1.0, count) * 2.0 * INSTANCE_JITTER, 0.0, 1.0)
    return height, dryness, maturity


def ladder_params(params, variant, variants):
    """Element parameters of variant of variants when the population picks variants by maturity: the seed-head and
    dry-tip shares rise from a quarter to 1.75 times the population's own, so their mean stays as given."""
    level = 2.0 * (variant + 0.5) / variants
    changed = dict(params)
    for key in ("seed_heads", "dry_tips"):
        if key in changed:
            changed[key] = float(min(1.0, changed[key] * level))
    return changed


def ladder_pick(maturity, variants):
    return numpy.minimum((maturity * variants).astype(int), variants - 1)
