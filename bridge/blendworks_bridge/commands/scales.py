"""The engrave_scale command: the tick marks of a dial cut or embossed in one boolean."""

import math

from .. import limits
from ..analytic_paths import DEFAULT_TOLERANCE
from ..cutters import add_solid
from ..engraving import cut, sampler_for
from ..errors import bad_args, failed
from ..limits import DIAL_MARKS, MARK_CLASSES, TURN, WINDING
from ..meshdata import MeshData
from ..registry import command
from ..schema import array, boolean, integer, length, number, obj as object_schema, ref, string
from ..surfaces import CylinderSurface, RingSurface
from ..util import check_vertex_cap, get_mesh_object
from .engrave import surface_properties

MAX_MARKS = DIAL_MARKS
ANGLE_EPSILON = 1e-9
DEFAULT_WIDTH = 0.0005
DEFAULT_LENGTH = 0.004
PLACES = ("above", "centre", "below")


def class_schema():
    schema = object_schema(
        {
            "every": integer("This class takes every n-th mark, counted from the first mark of the range (which every class takes).", 1, MAX_MARKS),
            "length": length("Mark length in metres across the circle: radially on a ring, along the axis on a cylinder."),
            "width": length("Mark width in metres along the circle."),
            "depth": length("Cut depth in metres, for a cut scale."),
            "height": length("Emboss height in metres, for an embossed scale."),
        },
        ["every"],
    )
    schema["description"] = "A mark class such as the major marks: its own length, width and depth or height. A mark takes the class with the largest every that divides its index."
    return schema


@command(
    "engrave_scale",
    "Cut or emboss the tick marks of a dial in one boolean: an angular range on a ring face or cylinder band, by step or count, with major classes and quadrant mirroring. Numbers: engrave.",
    {
        "name": ref(string("Mesh object to mark."), "object"),
        "ring": surface_properties()["ring"],
        "cylinder": surface_properties()["cylinder"],
        "start": number("Angle in degrees of the first mark, anticlockwise from the surface's reference.", -WINDING, WINDING, 0.0),
        "end": number("Angle in degrees of the last mark; a range of 360 degrees or more is a full circle, which leaves out the mark that would repeat the first.", -WINDING, WINDING, 360.0),
        "step": number("Degrees between marks.", -TURN, TURN),
        "count": integer("Number of marks, spread evenly from start to end.", 1, MAX_MARKS),
        "mirror": string("none, or quadrants: repeat the marks at 180 - a, 180 + a and 360 - a for every mark at angle a, as on a meridian ring numbered 0-90-0-90.", ["none", "quadrants"], "none"),
        "place": string("Where the marks sit on the circle: above (from it outward on a ring, along +axis on a cylinder), centre, or below.", list(PLACES), "above"),
        "length": length("Length of the ordinary marks in metres.", DEFAULT_LENGTH),
        "width": length("Width of the ordinary marks in metres.", DEFAULT_WIDTH),
        "depth": length("Cut depth of the ordinary marks in metres."),
        "height": length("Emboss height of the ordinary marks in metres."),
        "classes": array(class_schema(), "Mark classes with their own size, for example {every: 10, length: 0.008, depth: 0.0008} for major marks.", 0, MARK_CLASSES, []),
        "tolerance": length("Largest distance in metres between the curved surface and the flat facets of a mark.", DEFAULT_TOLERANCE),
        "clean": boolean("Run clean_mesh on the result.", True),
    },
    ["name"],
    slow=True,
    family="engraving",
    intents=("graduations or ticks around a ring", "degree divisions with longer major lines", "bezel or protractor gauge"),
    nearest=(("engrave", "for text, numbers and symbols"), ("instances", "to place separate objects around a circle")),
)
def engrave_scale(ctx, args):
    target = get_mesh_object(args["name"])
    if ("depth" in args) == ("height" in args):
        raise bad_args("give exactly one of depth (cut) or height (emboss)")
    cutting = "depth" in args
    surface = scale_surface(args)
    marks = mark_angles(args)
    classes = mark_classes(args, cutting)
    data = MeshData()
    sampler = sampler_for(target)
    inverse = target.matrix_world.inverted()
    tally = {}
    for angle, index in marks:
        size = pick_class(classes, index)
        tally[size["every"]] = tally.get(size["every"], 0) + 1
        x = surface.x_of_angle(angle)
        low, high = span(args["place"], size["length"])
        outline = [(-size["width"] / 2.0, low), (size["width"] / 2.0, low), (size["width"] / 2.0, high), (-size["width"] / 2.0, high)]
        depth, rise = reach(size, cutting, args["tolerance"])
        anchor = surface.point(x, (low + high) / 2.0)[0]
        material = target.data.polygons[target.closest_point_on_mesh(inverse @ anchor)[3]].material_index if target.data.polygons else 0
        add_solid(data, [(outline, [])], surface, (x, 0.0), depth, rise, material, 0.0, args["tolerance"], sampler)
        if len(data.verts) > limits.MAX_MESH_VERTICES:
            raise failed(f"the scale needs more than {limits.MAX_MESH_VERTICES} vertices; use fewer marks or a larger tolerance")
    check_vertex_cap(len(data.verts))
    result = cut(ctx, target, data, cutting, args["clean"], "the scale")
    result.update({
        "surface": surface.kind,
        "marks": len(marks),
        "angles": [round(angle, 9) for angle, _ in marks],
        "classes": [{"every": every, "marks": tally[every]} for every in sorted(tally)],
    })
    return result


def scale_surface(args):
    given = [kind for kind in ("ring", "cylinder") if kind in args]
    if len(given) != 1:
        raise bad_args("give the surface as exactly one of ring or cylinder")
    spec = {**args[given[0]], "angle": 0.0}
    return RingSurface(spec) if given[0] == "ring" else CylinderSurface(spec)


def source_angles(args):
    if ("step" in args) == ("count" in args):
        raise bad_args("give exactly one of step or count")
    start, end = args["start"], args["end"]
    full = abs(end - start) >= 360.0 - ANGLE_EPSILON
    if full:
        end = start + math.copysign(360.0, end - start)
    if "step" in args:
        step = args["step"]
        if step == 0 or (end - start) * step < 0:
            raise bad_args("step must not be zero and must run from start towards end")
        total = int(math.floor((end - start) / step + ANGLE_EPSILON)) + 1
        if full and abs(start + (total - 1) * step - end) < ANGLE_EPSILON:
            total -= 1
        check_marks(total)
        return [start + index * step for index in range(total)]
    count = args["count"]
    if count == 1:
        return [start]
    gap = (end - start) / (count if full else count - 1)
    return [start + index * gap for index in range(count)]


def check_marks(total):
    """Exact: total is the number of marks source_angles lists, counted before listing them."""
    if total > MAX_MARKS:
        raise bad_args(f"the scale has {total} marks; the {MAX_MARKS.key} limit is {MAX_MARKS.plain()} ({MAX_MARKS.reason}) "
                       "Raise step or narrow start to end.")


def mark_angles(args):
    sources = source_angles(args)
    check_marks(len(sources))
    marks = []
    seen = []
    for index, angle in enumerate(sources):
        copies = [angle] if args["mirror"] == "none" else [angle, 180.0 - angle, 180.0 + angle, 360.0 - angle]
        for copy in copies:
            wrapped = copy % 360.0
            if any(min(abs(wrapped - other), 360.0 - abs(wrapped - other)) < 1e-7 for other in seen):
                continue
            seen.append(wrapped)
            marks.append((copy, index))
    if len(marks) > MAX_MARKS:
        raise bad_args(f"the scale has {len(marks)} marks; the cap is {MAX_MARKS}")
    return marks


def mark_classes(args, cutting):
    field = "depth" if cutting else "height"
    base = {"every": 1, "length": args["length"], "width": args["width"], field: args[field]}
    classes = [base]
    for given in args["classes"]:
        other = "height" if cutting else "depth"
        if other in given:
            raise bad_args(f"a class of a {'cut' if cutting else 'embossed'} scale takes {field}, not {other}")
        if any(item["every"] == given["every"] for item in classes):
            raise bad_args(f"two classes take every {given['every']}")
        classes.append({**base, **given})
    return sorted(classes, key=lambda item: -item["every"])


def pick_class(classes, index):
    return next(item for item in classes if index % item["every"] == 0)


def span(place, size):
    return {"above": (0.0, size), "centre": (-size / 2.0, size / 2.0), "below": (-size, 0.0)}[place]


def reach(size, cutting, tolerance):
    if cutting:
        return size["depth"], max(0.3 * size["depth"], 4.0 * tolerance)
    return max(0.5 * size["height"], 4.0 * tolerance), size["height"]
