from .outlines import triangulate

MAX_REFINEMENTS = 8


def edge_key(a, b):
    return (a, b) if a < b else (b, a)


def pattern(triangle, marked):
    a, b, c = triangle
    flags = [edge_key(a, b) in marked, edge_key(b, c) in marked, edge_key(c, a) in marked]
    count = sum(flags)
    for _ in range(3):
        if (count == 1 and flags[0]) or (count == 2 and flags[0] and flags[1]):
            break
        a, b, c = b, c, a
        flags = flags[1:] + flags[:1]
    return (a, b, c), count


def refine(points, triangles, too_long):
    points = list(points)
    for _ in range(MAX_REFINEMENTS):
        marked = {edge_key(a, b) for tri in triangles for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])) if too_long(points[a], points[b])}
        if not marked:
            break
        middles = {}

        def middle(a, b):
            key = edge_key(a, b)
            if key not in middles:
                points.append(tuple((points[a][axis] + points[b][axis]) / 2.0 for axis in range(2)))
                middles[key] = len(points) - 1
            return middles[key]

        split = []
        for triangle in triangles:
            (a, b, c), count = pattern(triangle, marked)
            if count == 0:
                split.append((a, b, c))
            elif count == 1:
                m = middle(a, b)
                split.extend([(a, m, c), (m, b, c)])
            elif count == 2:
                p, q = middle(a, b), middle(b, c)
                split.extend([(p, b, q), (a, p, q), (a, q, c)])
            else:
                p, q, r = middle(a, b), middle(b, c), middle(c, a)
                split.extend([(a, p, r), (p, b, q), (r, q, c), (p, q, r)])
        triangles = split
    return points, triangles


def boundary_edges(triangles):
    directed = {(tri[index], tri[(index + 1) % 3]) for tri in triangles for index in range(3)}
    return [(a, b) for a, b in directed if (b, a) not in directed]


def add_solid(data, shapes, surface, shift, down, up, material, too_long):
    for outline, holes in shapes:
        points, triangles = triangulate(outline, holes)
        points, triangles = refine(points, triangles, too_long)
        mapped = [surface.point(x + shift[0], y + shift[1]) for x, y in points]
        high = [data.vertex(position + normal * up) for position, normal in mapped]
        low = [data.vertex(position - normal * down) for position, normal in mapped]
        for a, b, c in triangles:
            data.face((high[a], high[b], high[c]), None, 0, material, False)
            data.face((low[c], low[b], low[a]), None, 0, material, False)
        for a, b in boundary_edges(triangles):
            data.face((high[a], low[a], low[b], high[b]), None, 0, material, False)
    return data


def limiter(surface, tolerance):
    limit = surface.limit(tolerance)
    if limit == float("inf"):
        return lambda first, second: False
    return lambda first, second: surface.distance(first, second) > limit

