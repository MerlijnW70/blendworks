from ..builder import finish_shape
from ..kit_limits import MAX_PROFILE_POINTS
from ..registry import command
from ..schema import described, integer, length, number, obj, points2, string
from ..shell import shell_data
from ..shell_profile import SHAPES
from ..util import require_free_name
from .shapes import with_shape_fields

RIBS = described(
    obj(
        {
            "count": integer("Ribs per whorl.", 1, 64),
            "height": number("Rib height as a fraction of the local aperture size.", exclusive_minimum=0, maximum=0.5),
        },
        ["count", "height"],
    ),
    "Ridges across the growth direction, one crest per rib on every whorl.",
)

SPIRAL_RIDGES = described(
    obj(
        {
            "count": integer("Ridges around the profile.", 1, 64),
            "height": number("Ridge height as a fraction of the local aperture size.", exclusive_minimum=0, maximum=0.5),
        },
        ["count", "height"],
    ),
    "Ridges that run along the spiral, like the radial ribs of a fan shell.",
)

LIP = described(
    obj(
        {
            "flare": number("Growth of the profile at the aperture, as a fraction of the aperture size.", exclusive_minimum=0, maximum=2.0, default=0.3),
            "length": number("How much of the last whorl the lip takes, in turns.", 0.02, 1.0, 0.15),
            "thicken": number("Extra wall at the rim as a fraction of thickness; used with thickness.", 0.0, 4.0, 0.5),
        }
    ),
    "A flared, thickened rim at the aperture.",
)


@command(
    "shell",
    "Grow a closed Raup shell: a generating curve swept along a logarithmic helico-spiral, with ribs, ridges, a lip and an optional wall.",
    with_shape_fields(
        {
            "W": number("Expansion of the radius per whorl: the radius one whorl further on is W times larger.", 1.05, 100.0, 1.6),
            "D": number("Distance of the generating curve from the axis: its inner distance divided by its outer distance.", 0.01, 0.95, 0.3),
            "T": number("Translation along the axis per whorl, as a fraction of the distance of the curve's centre from the axis; 0 gives a flat coil, and the shell winds downwards with the apex at the top.", 0.0, 20.0, 1.0),
            "turns": number("Whorls from the apex to the aperture.", exclusive_minimum=0, maximum=24.0, default=4.0),
            "profile": string("Generating curve: circle, ellipse (with aspect) or points.", SHAPES, "circle"),
            "aspect": number("ellipse: height divided by width of the curve in the plane through the axis. Default 0.6.", 0.05, 20.0),
            "points": points2("points: the curve as [u, v] points in metres, u away from the axis and v along it, at the aperture; any winding.", 3, MAX_PROFILE_POINTS),
            "profile_segments": integer("circle, ellipse: points on the curve; a multiple of 4. Default 24.", 8, 256),
            "size": length("Size of the final aperture in metres: the larger extent of the generating curve at the end (before a lip). Default 0.1, or the extent of the given points."),
            "steps": integer("Rings per whorl.", 8, 360, 48),
            "ribs": RIBS,
            "spiral_ridges": SPIRAL_RIDGES,
            "lip": LIP,
            "thickness": length("Make a solid wall of at least this many metres with a hollow inside that opens at the aperture; the earliest whorls, too narrow to hollow, stay solid. Without it the aperture is closed flat."),
            "handedness": string("right: a right-handed screw (apex up, the aperture on the right); left: its mirror image.", ["right", "left"], "right"),
        },
        "Shell",
    ),
    slow=True,
    family="shapes",
    intents=("seashell, snail, conch, ammonite or nautilus", "logarithmic spiral shell that grows larger each whorl", "ribbed or ridged coiled shape"),
    nearest=(("sweep", "for a spring or coil of constant size"), ("lathe", "for parts turned around one axis")),
)
def shell(ctx, args):
    require_free_name(args["name"])
    data, info = shell_data(args)
    result = finish_shape(ctx, data, args)
    result.update({"rings": info["rings"], "tail_rings": info["tail_rings"], "points_per_ring": info["points_per_ring"], "turns": args["turns"]})
    if info["wall"] is not None:
        result.update({"wall_min": round(info["wall"], 9), "cavity_from_ring": info["cavity_from_ring"]})
    return result
