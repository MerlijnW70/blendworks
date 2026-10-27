import math

import bpy

from .. import limits
from ..analytic_paths import DEFAULT_TOLERANCE
from ..cutters import add_solid, limiter
from ..errors import bad_args, failed
from ..glyphs import bounds_of, load_font
from ..kit_limits import MAX_PATH_POINTS
from ..meshdata import MeshData
from ..registry import command
from ..schema import boolean, integer, length, number, obj as object_schema, point3, points3, string, vector3
from ..selection import EXTENDED_FACE_PROPERTIES
from ..surfaces import FaceRegion, build_surface
from ..textlayout import ALIGNS, VALIGNS, text_shapes
from ..topology import mesh_report
from ..util import check_vertex_cap, get_mesh_object, mesh_counts
from .clean import clean_object
from .modifiers import add_modifier, remove_stand_in

MAX_REPEATS = 720
DEFAULT_SIZE = 0.01


def surface_properties():
    plane = object_schema({"origin": point3("A point on the surface in metres; the text is anchored here."), "normal": vector3("Direction the surface faces."), "up": vector3("Direction of the top of the text. Default +Z, or +Y on a horizontal surface.")}, ["origin", "normal"])
    plane["description"] = "A flat surface."
    faces = object_schema({**EXTENDED_FACE_PROPERTIES, "up": vector3("Direction of the top of the text. Default +Z, or +Y on a horizontal region.")})
    faces["description"] = "A flat region chosen like any face selection; the text is anchored at its centre."
    cylinder = object_schema(
        {
            "centre": vector3("A point on the axis in metres.", [0.0, 0.0, 0.0]),
            "axis": vector3("Axis of the ring or cylinder; the top of the text points along it.", [0.0, 0.0, 1.0]),
            "radius": length("Radius of the surface in metres.", maximum=1000.0),
            "side": string("outer: the text reads on the outside; inner: on the inside of a ring.", ["outer", "inner"], "outer"),
            "angle": number("Angle in degrees around the axis where the text is anchored.", -36000.0, 36000.0, 0.0),
            "reference": vector3("Direction of angle 0, made perpendicular to the axis. Default +X, or +Y when the axis runs along X."),
        },
        ["radius"],
    )
    cylinder["description"] = "A cylinder or ring band: the text wraps around the axis."
    curve = object_schema(
        {
            "object": string("Name of a curve object (one spline) to follow."),
            "waypoints": points3("Path points [x, y, z] in metres, instead of a curve object.", 2, MAX_PATH_POINTS),
            "closed": boolean("Join the end of the path to its start."),
            "normal": vector3("Direction the text faces; the path must not run along it.", [0.0, 0.0, 1.0]),
        }
    )
    curve["description"] = "A path on the surface: the text follows it."
    return {"plane": plane, "faces": faces, "cylinder": cylinder, "curve": curve}


def repeat_schema():
    schema = object_schema(
        {
            "count": integer("How many copies.", 2, MAX_REPEATS),
            "step": number("Distance between copies: degrees around a cylinder, metres on other surfaces.", -100000.0, 100000.0),
            "number_start": number("Value of {n} in the first copy.", -1e9, 1e9, 0.0),
            "number_step": number("Add this to {n} for each copy; the text must contain {n}.", -1e9, 1e9),
        },
        ["count", "step"],
    )
    schema["description"] = "Repeat the text along the surface, for scales: a number every 10 degrees around a ring is count 36, step 10, number_step 10."
    return schema


def number_text(value):
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:g}"


def instance_texts(args):
    repeat = args.get("repeat")
    text = args["text"]
    if repeat is None:
        if "{n}" in text:
            raise bad_args("{n} counts the copies of a repeat; add repeat or write the number")
        return [text], [0.0]
    if repeat["step"] == 0:
        raise bad_args("repeat.step must not be zero")
    numbered = "number_step" in repeat
    if numbered != ("{n}" in text):
        raise bad_args("number_step and {n} in the text go together")
    texts = [text.replace("{n}", number_text(repeat["number_start"] + index * repeat["number_step"])) if numbered else text for index in range(repeat["count"])]
    return texts, [index * repeat["step"] for index in range(repeat["count"])]


def along(surface, args, step):
    if surface.kind == "cylinder":
        return args["offset"] + math.radians(step) * surface.radius
    return args["offset"] + step


def check_fit(surface, shapes, shift):
    if not isinstance(surface, FaceRegion):
        return None
    low_x, low_y, high_x, high_y = bounds_of(shapes)
    region = surface.region
    return region[0] - 1e-9 <= low_x + shift[0] and high_x + shift[0] <= region[2] + 1e-9 and region[1] - 1e-9 <= low_y + shift[1] and high_y + shift[1] <= region[3] + 1e-9


@command(
    "engrave",
    "Cut or emboss text and symbols (a built-in set: zodiac signs and planets) into a mesh along a plane, face region, cylinder band or curve, with optional repeats for scales.",
    {
        "name": string("Mesh object to engrave."),
        "text": string("The text. {aries}, {sun} and the like, or the Unicode signs, give built-in symbols; {n} is the repeat number.", max_length=limits.MAX_TEXT_LENGTH),
        **surface_properties(),
        "size": length("Letter size in metres, as text_object's size.", DEFAULT_SIZE, 1000.0),
        "depth": length("Cut this deep into the surface, in metres.", maximum=1000.0),
        "height": length("Emboss this high above the surface, in metres.", maximum=1000.0),
        "spacing": number("Letter spacing factor; 1 is the font's own.", 0.1, 10.0, 1.0),
        "align": string("Which part of the text sits at the anchor.", list(ALIGNS), "centre"),
        "valign": string("middle: half a letter height above the anchor line; baseline: the text sits on it.", list(VALIGNS), "middle"),
        "rotation": number("Turn the text by this many degrees on the surface.", -360.0, 360.0, 0.0),
        "offset": number("Move the text along the path, in metres: round a cylinder along the arc.", -10000.0, 10000.0, 0.0),
        "shift": number("Move the text across the path, in metres; positive is towards the top of the text.", -10000.0, 10000.0, 0.0),
        "font": string("A .ttf, .otf, .woff or .woff2 file in the workspace. Default: Blender's bundled font."),
        "repeat": repeat_schema(),
        "tolerance": length("Largest distance in metres between a curved surface and the flat facets of the cutter.", DEFAULT_TOLERANCE, 1.0),
        "clean": boolean("Run clean_mesh on the result.", True),
    },
    ["name", "text"],
    slow=True,
)
def engrave(ctx, args):
    target = get_mesh_object(args["name"])
    if ("depth" in args) == ("height" in args):
        raise bad_args("give exactly one of depth (cut) or height (emboss)")
    cutting = "depth" in args
    surface = build_surface(target, args)
    texts, steps = instance_texts(args)
    font = load_font(ctx, args["font"]) if "font" in args else None
    try:
        data, summary = build_cutters(ctx, target, surface, args, texts, steps, font, cutting)
    finally:
        if font is not None:
            bpy.data.fonts.remove(font)
    check_vertex_cap(len(data.verts))
    before = mesh_report(target.data)
    apply_cutters(ctx, target, data, cutting)
    cleaned = clean_object(target) if args["clean"] else None
    after = mesh_report(target.data)
    if before["volume"] is not None and after["volume"] is not None and abs(after["volume"] - before["volume"]) <= 1e-12 * abs(before["volume"]):
        raise failed(f"the engraving did not change {target.name}: the {surface.kind} surface does not meet the mesh, so check its position")
    if before["manifold"] and not after["manifold"]:
        raise failed("the engraving left the mesh open; try a smaller depth, a larger tolerance or a surface that matches the mesh")
    result = {
        "name": target.name,
        "mode": "cut" if cutting else "emboss",
        "instances": len(texts),
        "mesh": mesh_counts(target.data),
        "manifold": after["manifold"],
        "volume_before": rounded_volume(before),
        "volume_after": rounded_volume(after),
        "volume_change": rounded_volume(after, before),
        "fits": summary["fits"],
        "surface": surface.kind,
    }
    if cleaned is not None:
        result["cleaned"] = {key: value for key, value in cleaned.items() if key not in ("mesh", "manifold", "volume")}
    if target.data.uv_layers:
        result["note"] = "the new faces have no UVs; unwrap the object again"
    return result


def rounded_volume(report, other=None):
    if report["volume"] is None or (other is not None and other["volume"] is None):
        return None
    return round(report["volume"] - (other["volume"] if other is not None else 0.0), 12)


def build_cutters(ctx, target, surface, args, texts, steps, font, cutting):
    tolerance = args["tolerance"]
    size = args["size"]
    depth = args["depth"] if cutting else max(0.5 * args["height"], 4.0 * tolerance)
    rise = max(0.3 * args["depth"], 4.0 * tolerance) if cutting else args["height"]
    too_long = limiter(surface, tolerance)
    cache = {}
    data = MeshData()
    fits = True
    inverse = target.matrix_world.inverted()
    for text, step in zip(texts, steps):
        if text not in cache:
            cache[text] = text_shapes(ctx, text, size, args["spacing"], font, args["align"], args["valign"], args["rotation"])[0]
        shapes = cache[text]
        shift = (along(surface, args, step), args["shift"])
        anchor = surface.point(shift[0], shift[1])[0]
        material = target.data.polygons[target.closest_point_on_mesh(inverse @ anchor)[3]].material_index if target.data.polygons else 0
        fit = check_fit(surface, shapes, shift)
        fits = fits and fit is not False
        add_solid(data, shapes, surface, shift, depth, rise, material, too_long)
        if len(data.verts) > limits.MAX_MESH_VERTICES:
            raise failed(f"the engraving needs more than {limits.MAX_MESH_VERTICES} vertices; use less text or a larger tolerance")
    return data, {"fits": fits if isinstance(surface, FaceRegion) else None}


def apply_cutters(ctx, target, data, cutting):
    mesh = bpy.data.meshes.new("blendworks_engrave_cutter")
    data.to_mesh(mesh)
    cutter = bpy.data.objects.new("blendworks_engrave_cutter", mesh)
    ctx.scene.collection.objects.link(cutter)
    try:
        settings = {"operation": "DIFFERENCE" if cutting else "UNION", "solver": "EXACT", "object": cutter, "use_self": True}
        add_modifier(ctx, target, "BOOLEAN", settings, True)
    finally:
        remove_stand_in(cutter)
