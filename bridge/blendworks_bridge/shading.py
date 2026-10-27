import math

SHADING = ("auto", "smooth", "flat")
FLAT_RATIO = 3.0


def hard_corners(points, closed):
    """Indices of profile points where a segment is much longer than the next: the long one is a flat face, so it must not shade into the rounding beside it."""
    count = len(points)
    lengths = [math.dist(points[index], points[(index + 1) % count]) for index in range(count if closed else count - 1)]
    corners = set()
    for index in range(count):
        if not closed and index in (0, count - 1):
            continue
        before, after = lengths[index - 1], lengths[index % len(lengths)]
        if max(before, after) > FLAT_RATIO * min(before, after):
            corners.add(index)
    return corners


def apply_shading(bm, mode, angle_degrees):
    if mode == "flat":
        for face in bm.faces:
            face.smooth = False
        for edge in bm.edges:
            edge.smooth = True
        return
    threshold = math.radians(angle_degrees)
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        if mode == "smooth" or len(edge.link_faces) != 2:
            edge.smooth = True
        else:
            edge.smooth = edge.smooth and edge.calc_face_angle(0.0) <= threshold
