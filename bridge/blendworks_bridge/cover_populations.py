"""Ground cover populations: merging presets with the caller's kind groups."""

from .commands.scatter import NOISE
from .cover_kinds import BLADE_KINDS, ELEMENT, KINDS, LITTER_KINDS, element_params
from .cover_presets import PRESET_POPULATIONS
from .errors import bad_args
from .limits import (BASE_NAME_LENGTH, FRACTION, HALF_TURN, HEIGHT_BAND, LEAST_CLUMP_SIZE, LEAST_WIDENING,
                     MAX_ATTRIBUTE_VALUE, MAX_CLUMP_SIZE, MAX_COVER_DENSITY, MAX_DISTANCE_MASKS, MAX_ELEMENT_TRIANGLES,
                     MAX_ELEMENT_VARIANTS, MAX_LENGTH, MAX_POPULATIONS as POPULATION_LIMIT, MAX_RELIEF,
                     MAX_SCALE_FACTOR, MAX_WIDENING, QUARTER_TURN, SMALLEST_COVER_PATCH,
                     SMALLEST_INSTANCE_SCALE)
from .liquid_masks import MODES as LIQUID_MODES
from .meadow_rules import FIELD_PROPERTIES, check_responses
from .schema import EXISTS, array, boolean, described, integer, names, number, obj, ref, string, validate

FORM_CHOICES = ("auto", "geometry", "cards")
MAX_POPULATIONS = POPULATION_LIMIT


def pair(description, low, high):
    return array({"type": "number", "minimum": low, "maximum": high}, description, 2, 2)


DISTANCE = described(
    obj(
        {
            "objects": ref(names("Mesh objects to measure the distance to (their evaluated surfaces in world space; a point inside counts as a negative distance)."), "object", EXISTS),
            "min": number("Keep elements at least this many metres from the surfaces, so none grow inside a trunk or a rock.", -MAX_LENGTH, MAX_LENGTH),
            "max": number("Keep elements at most this many metres from the surfaces, as litter under trees.", -MAX_LENGTH, MAX_LENGTH),
            "edge": number("Soft edge in metres inside the limits.", 0.0, MAX_LENGTH, 0.0),
        },
        ["objects"],
    ),
    "A distance mask: density 1 between min and max metres from the objects, 0 outside.",
)

POPULATION = described(
    obj(
        {
            "name": string("Name of the population, unique in this call; with a preset, a preset population of this name is changed instead of a new one added.", max_length=BASE_NAME_LENGTH),
            "element": string("Element kind.", list(KINDS)),
            "params": described(ELEMENT, "Element parameters; each kind takes its own fields and has its own defaults."),
            "variants": integer("Different element meshes, each from its own seed; every instance picks one.", 1, MAX_ELEMENT_VARIANTS),
            "triangles": integer("Triangle budget per element; the generator fits its detail into it.", 1, MAX_ELEMENT_TRIANGLES),
            "form": string("geometry: real blades, petals and leaves; cards: alpha-mapped cards; auto: geometry up to card_distance from the camera or point, cards beyond.", list(FORM_CHOICES)),
            "card_distance": number("auto: distance in metres from the camera or point where cards take over.", 0.0, MAX_LENGTH),
            "density": number("Elements per square metre where every mask is 1 and the camera falloff is full.", exclusive_minimum=0.0, maximum=MAX_COVER_DENSITY),
            "clumping": described(obj({"radius": number("Radius in metres that holds most of a clump (two standard deviations of a Thomas cluster process).", SMALLEST_COVER_PATCH, MAX_LENGTH), "per_clump": number("Mean elements per clump.", LEAST_CLUMP_SIZE, MAX_CLUMP_SIZE)}, ["radius", "per_clump"]), "Gather the elements in clumps around random centres; the mean density stays density."),
            "slope": pair("Keep elements where the surface normal is between these angles from vertical, in degrees.", 0.0, HALF_TURN),
            "slope_edge": number("Soft edge of the slope mask in degrees, inside its limits.", 0.0, QUARTER_TURN, 4.0),
            "height_range": pair("Keep elements between these world heights in metres.", -HEIGHT_BAND, HEIGHT_BAND),
            "height_edge": number("Soft edge of the height mask in metres, inside its limits.", 0.0, MAX_RELIEF, 0.0),
            "attribute": described(obj({"name": string("Float attribute of the target, such as erosion, deposition, slope or curvature."), "range": pair("Density rises from 0 at the first value to 1 at the second; give them the other way round to fall.", -MAX_ATTRIBUTE_VALUE, MAX_ATTRIBUTE_VALUE)}, ["name", "range"]), "An attribute mask."),
            "distance": array(DISTANCE, "Distance masks; they multiply.", 1, MAX_DISTANCE_MASKS),
            "avoid": number("Keep this many metres clear of the obstacles of the call; the density then rises linearly to full over avoid_falloff.", 0.0, MAX_LENGTH),
            "avoid_falloff": number("Distance in metres beyond avoid over which the density rises from 0 to full, so cover thins gradually towards a rock or trunk.", 0.0, MAX_LENGTH, 0.3),
            "hug": number("Keep within this many metres of the obstacles of the call (not inside them), for tufts or litter at the base of rocks and trunks; skipped when no obstacles are given.", 0.0, MAX_LENGTH),
            "under": number("Keep within this many metres of the trees of the call; skipped when no trees are given.", 0.0, MAX_LENGTH),
            "noise": NOISE,
            "liquid": string("Water from liquid_body or liquid_fill: avoid keeps the population out of it (the default), shore keeps it within shore metres of the water line, ignore grows it anyway.", list(LIQUID_MODES)),
            "shore": number("shore: width in metres of the band above the water line the population keeps to.", SMALLEST_COVER_PATCH, MAX_LENGTH),
            "scale_range": pair("Smallest and largest uniform scale of an instance.", SMALLEST_INSTANCE_SCALE, MAX_SCALE_FACTOR),
            "color_variation": number("Colour change from instance to instance, 0 to 1, through the gc_tint instance attribute.", 0.0, FRACTION),
            "align": number("0 keeps elements upright, 1 tilts them with the slope.", 0.0, FRACTION),
            "tilt": number("Random lean of each element in degrees.", 0.0, QUARTER_TURN),
            "embed": number("Depth in metres, times the scale, the base sinks below the surface; tilted bases sink further so no edge floats.", 0.0, MAX_RELIEF),
            "widen": boolean("Widen sparse far elements across by the inverse square root of the falloff, so the ground stays covered."),
            "max_widen": number("Largest widening factor.", LEAST_WIDENING, MAX_WIDENING, 2.0),
            **FIELD_PROPERTIES,
        },
        ["name"],
    ),
    "One layer of ground cover: an element kind with its density, masks and variation.",
)

KIND_POPULATION = {
    "blade": {"liquid": "avoid", "shore": 1.0, "form": "auto", "card_distance": 8.0, "scale_range": [0.8, 1.2], "color_variation": 0.5, "align": 0.35, "tilt": 8.0, "embed": 0.01, "widen": True, "variants": 4},
    "flower": {"liquid": "avoid", "shore": 1.0, "form": "auto", "card_distance": 8.0, "scale_range": [0.8, 1.15], "color_variation": 0.35, "align": 0.15, "tilt": 6.0, "embed": 0.01, "widen": False, "variants": 4},
    "litter": {"liquid": "avoid", "shore": 1.0, "form": "geometry", "card_distance": 8.0, "scale_range": [0.7, 1.3], "color_variation": 0.6, "align": 1.0, "tilt": 0.0, "embed": 0.001, "widen": False, "variants": 4},
}


def kind_group(kind):
    if kind in BLADE_KINDS:
        return "blade"
    return "litter" if kind in LITTER_KINDS else "flower"


def complete(entry):
    population = validate(POPULATION, entry)
    if "element" not in population or "density" not in population:
        raise bad_args(f"population {population['name']} needs element and density")
    filled = dict(KIND_POPULATION[kind_group(population["element"])], **population)
    filled["params"] = element_params(filled["element"], population.get("params", {}))
    for key in ("scale_range", "slope", "height_range"):
        if key in filled and filled[key][0] > filled[key][1]:
            raise bad_args(f"population {filled['name']}: {key} must be [smallest, largest]")
    for spec in filled.get("distance", []):
        if "min" not in spec and "max" not in spec:
            raise bad_args(f"population {filled['name']}: a distance mask needs min or max")
    check_responses(filled, bad_args)
    return filled


def merged(preset, given):
    base = {entry["name"]: dict(entry) for entry in PRESET_POPULATIONS[preset]} if preset else {}
    order = list(base)
    for entry in given:
        if entry["name"] in base:
            update = dict(entry)
            if "params" in update:
                update["params"] = dict(base[entry["name"]].get("params", {}), **update["params"])
            base[entry["name"]].update(update)
        else:
            base[entry["name"]] = dict(entry)
            order.append(entry["name"])
    return [base[name] for name in order]


def resolved_populations(args):
    given = args.get("populations", [])
    names_given = [entry["name"] for entry in given]
    if len(set(names_given)) != len(names_given):
        raise bad_args("a population name is used twice")
    entries = merged(args.get("preset"), given)
    if not entries:
        raise bad_args("give a preset or at least one population")
    if len(entries) > MAX_POPULATIONS:
        raise bad_args(f"at most {MAX_POPULATIONS} populations")
    scale = args["density_scale"]
    populations, skipped = [], []
    for entry in entries:
        population = complete(entry)
        population["density"] *= scale
        masks = list(population.get("distance", []))
        if population.get("avoid") and args.get("obstacles"):
            masks.append({"objects": args["obstacles"], "min": population["avoid"], "edge": population["avoid_falloff"]})
        if "hug" in population:
            if not args.get("obstacles"):
                skipped.append(population["name"])
                continue
            masks.append({"objects": args["obstacles"], "min": 0.0, "edge": 0.0})
            masks.append({"objects": args["obstacles"], "max": population["hug"], "edge": 0.5 * population["hug"]})
        if "under" in population:
            if not args.get("trees"):
                skipped.append(population["name"])
                continue
            masks.append({"objects": args["trees"], "min": 0.0, "edge": 0.0})
            masks.append({"objects": args["trees"], "max": population["under"], "edge": 0.3 * population["under"]})
        if masks:
            population["distance"] = masks
        populations.append(population)
    if not populations:
        raise bad_args("every population was skipped: they need trees or obstacles that were not given")
    return populations, skipped
