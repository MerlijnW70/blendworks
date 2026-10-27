import bpy
from mathutils import Vector

from .errors import bad_args, failed
from .glyph_data import GLYPHS
from .outlines import clockwise, counter_clockwise, inside, signed_area

UNIT = 1000.0
CAP_HEIGHT = 0.682
SYMBOL_SCALE = 1.3115
ZODIAC = ("aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")
PLANETS = ("sun", "moon", "mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto")
CHARACTERS = {
    character: name
    for character, name in zip("♈♉♊♋♌♍♎♏♐♑♒♓", ZODIAC)
}
CHARACTERS.update({character: name for character, name in zip("☉☽☿♀⊕♂♃♄♅♆♇", PLANETS)})
FLATNESS = 0.0005
MAX_SPLIT_DEPTH = 10
FONT_EXTENSIONS = (".ttf", ".otf", ".woff", ".woff2")


def symbol_names():
    return ZODIAC + PLANETS


def symbol_loops(name, size):
    advance, raw = GLYPHS[name]
    scale = size * SYMBOL_SCALE / UNIT
    loops = [[(raw_loop[index] * scale, raw_loop[index + 1] * scale) for index in range(0, len(raw_loop), 2)] for raw_loop in raw]
    return loops, advance * scale


def segment_distance(point, start, end):
    span = end - start
    if span.length_squared < 1e-24:
        return (point - start).length
    return abs((point - start).cross(span)) / span.length


def flatten_bezier(start, handle_a, handle_b, end, tolerance, depth=0):
    deviation = max(segment_distance(handle_a, start, end), segment_distance(handle_b, start, end))
    if depth >= MAX_SPLIT_DEPTH or deviation <= tolerance:
        return [end]
    a, b, c = (start + handle_a) / 2, (handle_a + handle_b) / 2, (handle_b + end) / 2
    d, e = (a + b) / 2, (b + c) / 2
    middle = (d + e) / 2
    return flatten_bezier(start, a, d, middle, tolerance, depth + 1) + flatten_bezier(middle, e, c, end, tolerance, depth + 1)


def spline_loop(spline, tolerance):
    points = spline.bezier_points
    loop = []
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        loop.append(Vector(point.co[:2]))
        loop.extend(flatten_bezier(Vector(point.co[:2]), Vector(point.handle_right[:2]), Vector(following.handle_left[:2]), Vector(following.co[:2]), tolerance)[:-1])
    return [(vertex.x, vertex.y) for vertex in loop]


def curve_loops(curve, tolerance):
    loops = []
    for spline in curve.splines:
        if spline.type == "BEZIER" and spline.use_cyclic_u and len(spline.bezier_points) >= 2:
            loop = spline_loop(spline, tolerance)
            if len(loop) >= 3 and abs(signed_area(loop)) > 1e-18:
                loops.append(loop)
    return loops


def text_loops(ctx, text, size, spacing, font):
    curve = bpy.data.curves.new("blendworks_engrave_text", "FONT")
    holder = None
    evaluated = None
    try:
        curve.body = text
        curve.size = size
        curve.space_character = spacing
        if font is not None:
            curve.font = font
        holder = bpy.data.objects.new("blendworks_engrave_text", curve)
        ctx.scene.collection.objects.link(holder)
        graph = ctx.depsgraph()
        evaluated = holder.evaluated_get(graph)
        return curve_loops(evaluated.to_curve(graph), FLATNESS * size)
    finally:
        if evaluated is not None:
            evaluated.to_curve_clear()
        if holder is not None:
            bpy.data.objects.remove(holder)
        bpy.data.curves.remove(curve)


def load_font(ctx, path):
    resolved = ctx.workspace.existing(path, FONT_EXTENSIONS)
    try:
        return bpy.data.fonts.load(resolved)
    except RuntimeError as error:
        raise bad_args(f"{path} is not a font Blender can read: {error}") from error


def nest(loops):
    depths = [sum(1 for other, candidate in enumerate(loops) if other != index and inside(loop[0], candidate)) for index, loop in enumerate(loops)]
    shapes = []
    for index, loop in enumerate(loops):
        if depths[index] % 2:
            continue
        holes = [loops[other] for other in range(len(loops)) if depths[other] == depths[index] + 1 and inside(loops[other][0], loop)]
        shapes.append((counter_clockwise(loop), [clockwise(hole) for hole in holes]))
    if not shapes:
        raise failed("the text has no outlines to engrave")
    return shapes


def bounds_of(shapes):
    xs = [x for outline, _ in shapes for x, _ in outline]
    ys = [y for outline, _ in shapes for _, y in outline]
    return min(xs), min(ys), max(xs), max(ys)
