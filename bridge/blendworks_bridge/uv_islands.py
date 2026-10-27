import heapq

import numpy

SAME_UV = 1e-6
FIT_ERROR = 0.05
SCALE_RANGE = (0.2, 5.0)
OVERLAP_EPSILON = 1e-7
TINY = 1e-18
COMPLEX = numpy.array([1.0, 1j])
PAIRWISE_FROM = 8
NEXT_CORNER = [1, 2, 0]


def edge_axes(triangles):
    edges = triangles[:, NEXT_CORNER] - triangles
    axes = numpy.stack([-edges[..., 1], edges[..., 0]], axis=-1)
    return axes / numpy.maximum(numpy.linalg.norm(edges, axis=-1, keepdims=True), TINY)


def separated(first, second, axes):
    mine = numpy.einsum("pjc,pac->paj", first, axes)
    theirs = numpy.einsum("pjc,pac->paj", second, axes)
    return ((theirs.min(axis=2) >= mine.max(axis=2) - OVERLAP_EPSILON) | (theirs.max(axis=2) <= mine.min(axis=2) + OVERLAP_EPSILON)).any(axis=1)


def any_overlap(triangles, others):
    if len(triangles) == 0 or len(others) == 0:
        return False
    low, high = triangles.min(axis=1), triangles.max(axis=1)
    near = (others.max(axis=1)[None] > low[:, None] + OVERLAP_EPSILON).all(axis=2) & (others.min(axis=1)[None] < high[:, None] - OVERLAP_EPSILON).all(axis=2)
    pairs = numpy.nonzero(near)
    if len(pairs[0]) == 0:
        return False
    first, second = triangles[pairs[0]], others[pairs[1]]
    apart = separated(first, second, edge_axes(first)) | separated(first, second, edge_axes(second))
    return not bool(apart.all())


class UVGraph:
    def __init__(self, obj, layer):
        mesh = obj.data
        self.mesh = mesh
        self.obj = obj
        faces, loops = len(mesh.polygons), len(mesh.loops)
        self.start = self.read(mesh.polygons, "loop_start", faces, numpy.int64)
        self.total = self.read(mesh.polygons, "loop_total", faces, numpy.int64)
        self.loop_vertex = self.read(mesh.loops, "vertex_index", loops, numpy.int64)
        self.loop_edge = self.read(mesh.loops, "edge_index", loops, numpy.int64)
        self.uv = self.read(layer.uv, "vector", loops * 2, numpy.float64).reshape(-1, 2)
        scale = obj.matrix_world.to_scale()
        self.area = self.read(mesh.polygons, "area", faces, numpy.float64) * abs(scale.x * scale.y * scale.z) ** (2.0 / 3.0)
        self.face_of_loop = numpy.repeat(numpy.arange(faces), self.total)
        mesh.calc_loop_triangles()
        count = len(mesh.loop_triangles)
        self.triangle_loops = self.read(mesh.loop_triangles, "loops", count * 3, numpy.int64).reshape(-1, 3)
        self.triangle_face = self.read(mesh.loop_triangles, "polygon_index", count, numpy.int64)
        self.seams = self.read(mesh.edges, "use_seam", len(mesh.edges), bool)
        self.edge_length = self.edge_lengths(mesh)
        self.edge_loops = {}
        for loop, edge in enumerate(self.loop_edge.tolist()):
            self.edge_loops.setdefault(edge, []).append(loop)
        self.lists = None
        self.labels = self.find_labels()

    @staticmethod
    def read(collection, name, count, dtype):
        values = numpy.empty(count, dtype=dtype)
        collection.foreach_get(name, values)
        return values

    def edge_lengths(self, mesh):
        points = self.read(mesh.vertices, "co", len(mesh.vertices) * 3, numpy.float64).reshape(-1, 3)
        ends = self.read(mesh.edges, "vertices", len(mesh.edges) * 2, numpy.int64).reshape(-1, 2)
        return numpy.linalg.norm(points[ends[:, 0]] - points[ends[:, 1]], axis=1)

    def following(self, loop):
        face = int(self.face_of_loop[loop])
        start, total = int(self.start[face]), int(self.total[face])
        return start + (loop - start + 1) % total

    def matching(self, loop, other, vertex):
        return other if self.loop_vertex[other] == vertex else self.following(other)

    def following_all(self, loops):
        start = self.start[self.face_of_loop[loops]]
        return start + (loops - start + 1) % self.total[self.face_of_loop[loops]]

    def continuous_pairs(self):
        pairs = numpy.array([loops for loops in self.edge_loops.values() if len(loops) == 2], dtype=numpy.int64).reshape(-1, 2)
        first, second = pairs[:, 0], pairs[:, 1]
        joined = numpy.ones(len(pairs), dtype=bool)
        for loop in (first, self.following_all(first)):
            partner = numpy.where(self.loop_vertex[second] == self.loop_vertex[loop], second, self.following_all(second))
            joined &= ~(numpy.abs(self.uv[loop] - self.uv[partner]).max(axis=1) > SAME_UV)
        faces = self.face_of_loop[pairs[joined]]
        return faces.tolist()

    def find_labels(self):
        parent = list(range(len(self.start)))

        def find(item):
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        for first, second in self.continuous_pairs():
            parent[find(first)] = find(second)
        names = {}
        return numpy.array([names.setdefault(find(face), len(names)) for face in range(len(parent))], dtype=numpy.int64)

    def members(self):
        groups = {}
        for face, label in enumerate(self.labels.tolist()):
            groups.setdefault(label, []).append(face)
        return groups

    def triangle_uv_area(self):
        corners = self.uv[self.triangle_loops]
        first, second = corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
        return 0.5 * numpy.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])

    def island_uv_areas(self):
        totals = numpy.zeros(int(self.labels.max()) + 1)
        numpy.add.at(totals, self.labels[self.triangle_face], self.triangle_uv_area())
        return totals

    def island_world_areas(self):
        totals = numpy.zeros(int(self.labels.max()) + 1)
        numpy.add.at(totals, self.labels, self.area)
        return totals

    def loops_of(self, faces):
        return numpy.concatenate([numpy.arange(self.start[face], self.start[face] + self.total[face]) for face in faces])

    def signed_area(self, faces):
        total = 0.0
        for face in faces:
            points = self.uv[self.start[face] : self.start[face] + self.total[face]]
            shifted = numpy.roll(points, -1, axis=0)
            total += 0.5 * float((points[:, 0] * shifted[:, 1] - shifted[:, 0] * points[:, 1]).sum())
        return total

    def boundary(self, faces, label):
        if self.lists is None:
            self.lists = (self.start.tolist(), self.total.tolist(), self.loop_edge.tolist(), self.face_of_loop.tolist(), self.seams.tolist())
        starts, totals, loop_edges, face_of_loop, seams = self.lists
        labels = self.labels
        found = {}
        for face in faces:
            for loop in range(starts[face], starts[face] + totals[face]):
                edge = loop_edges[loop]
                others = [item for item in self.edge_loops[edge] if item != loop]
                if seams[edge] or len(others) != 1:
                    continue
                neighbour = int(labels[face_of_loop[others[0]]])
                if neighbour != label:
                    found.setdefault(neighbour, []).append((loop, others[0], edge))
        return found

    def write(self):
        self.obj.data.uv_layers.active.uv.foreach_set("vector", self.uv.reshape(-1))
        self.mesh.update()


def edge_pairs(graph, links):
    pairs = {}
    for loop, other, _ in links:
        for corner in (loop, graph.following(loop)):
            vertex = int(graph.loop_vertex[corner])
            pairs[vertex] = (graph.uv[corner].copy(), graph.uv[graph.matching(loop, other, vertex)].copy())
    return pairs


def similarity(source, target):
    source_mean, target_mean = source.mean(axis=0), target.mean(axis=0)
    z = (source - source_mean) @ COMPLEX
    w = (target - target_mean) @ COMPLEX
    energy = float((numpy.abs(z) ** 2).sum())
    if energy < TINY:
        return None
    factor = complex((numpy.conj(z) * w).sum() / energy)
    error = float(numpy.abs(factor * z - w).max())
    return factor, error, float(numpy.abs(w).max()), source_mean, target_mean


def moved(points, factor, source_mean, target_mean):
    rotated = factor * ((points - source_mean) @ COMPLEX)
    return numpy.stack([rotated.real, rotated.imag], axis=1) + target_mean


def loop_cross(graph):
    loops = numpy.arange(len(graph.loop_vertex))
    first = graph.start[graph.face_of_loop]
    following = first + (loops - first + 1) % graph.total[graph.face_of_loop]
    points, shifted = graph.uv, graph.uv[following]
    return points[:, 0] * shifted[:, 1] - shifted[:, 0] * points[:, 1]


def face_half_cross(graph, faces):
    faces = numpy.asarray(faces, dtype=numpy.int64)
    halves = numpy.empty(len(faces))
    for index, face in enumerate(faces.tolist()):
        halves[index] = graph.signed_area((face,))
    return halves


def ordered_sum(start, values):
    return float(numpy.cumsum(numpy.concatenate(([start], values)))[-1])


class Islands:
    def __init__(self, graph):
        self.graph = graph
        faces = len(graph.start)
        cross = loop_cross(graph)
        halves = numpy.empty(faces)
        simple = graph.total < PAIRWISE_FROM
        if faces > 0:
            sums = numpy.add.reduceat(cross, graph.start) if len(cross) else numpy.zeros(faces)
            halves[:] = 0.5 * sums
        long_faces = numpy.nonzero(~simple)[0]
        if len(long_faces):
            halves[long_faces] = face_half_cross(graph, long_faces)
        self.half = halves
        order = numpy.argsort(graph.triangle_face, kind="stable")
        counts = numpy.bincount(graph.triangle_face, minlength=faces)
        starts = numpy.concatenate(([0], numpy.cumsum(counts)[:-1]))
        self.triangles_by_face = (order, starts, counts)
        self.areas = {}
        self.triangles = {}
        self.boxes = {}
        self.position = numpy.zeros(len(graph.loop_vertex), dtype=numpy.int64)

    def face_triangles(self, faces):
        order, starts, counts = self.triangles_by_face
        if not faces:
            return numpy.empty(0, dtype=numpy.int64)
        picked = numpy.asarray(faces, dtype=numpy.int64)
        lengths = counts[picked]
        offsets = numpy.repeat(starts[picked] - numpy.concatenate(([0], numpy.cumsum(lengths)[:-1])), lengths)
        return order[numpy.arange(int(lengths.sum())) + offsets]

    def signed_area(self, label, faces):
        if label not in self.areas:
            self.areas[label] = ordered_sum(0.0, self.half[numpy.asarray(faces, dtype=numpy.int64)])
        return self.areas[label]

    def triangles_of(self, label, faces):
        if label not in self.triangles:
            self.triangles[label] = self.face_triangles(faces)
        return self.triangles[label]

    def triangle_boxes(self, label, faces):
        if label not in self.boxes:
            self.boxes[label] = self.fresh_boxes(self.triangles_of(label, faces))
        return self.boxes[label]

    def fresh_boxes(self, triangles):
        corners = self.graph.uv[self.graph.triangle_loops[triangles]]
        return corners.min(axis=1), corners.max(axis=1)

    def near(self, label, faces, points):
        triangles = self.triangles_of(label, faces)
        if len(triangles) == 0:
            return numpy.empty((0, 3, 2))
        low, high = self.triangle_boxes(label, faces)
        least, most = points.min(axis=0), points.max(axis=0)
        close = (high > least + OVERLAP_EPSILON).all(axis=1) & (low < most - OVERLAP_EPSILON).all(axis=1)
        return self.graph.uv[self.graph.triangle_loops[triangles[close]]]

    def merge(self, small, small_faces, big, big_faces):
        moved_faces = numpy.asarray(small_faces, dtype=numpy.int64)
        self.half[moved_faces] = face_half_cross(self.graph, moved_faces) if numpy.any(self.graph.total[moved_faces] >= PAIRWISE_FROM) else self.fresh_halves(moved_faces)
        self.areas[big] = ordered_sum(self.signed_area(big, big_faces), self.half[moved_faces])
        small_triangles = self.triangles_of(small, small_faces)
        if big in self.boxes:
            big_low, big_high = self.boxes[big]
            small_low, small_high = self.fresh_boxes(small_triangles)
            self.boxes[big] = (numpy.concatenate((big_low, small_low)), numpy.concatenate((big_high, small_high)))
        self.triangles[big] = numpy.concatenate((self.triangles_of(big, big_faces), small_triangles))
        for cache in (self.areas, self.triangles, self.boxes):
            cache.pop(small, None)

    def fresh_halves(self, faces):
        graph = self.graph
        loops = graph.loops_of(faces)
        first = graph.start[graph.face_of_loop[loops]]
        following = first + (loops - first + 1) % graph.total[graph.face_of_loop[loops]]
        points, shifted = graph.uv[loops], graph.uv[following]
        cross = points[:, 0] * shifted[:, 1] - shifted[:, 0] * points[:, 1]
        bounds = numpy.concatenate(([0], numpy.cumsum(graph.total[faces])[:-1]))
        return 0.5 * numpy.add.reduceat(cross, bounds)


def attach(graph, islands, small, big, links):
    small_label, small_faces = small
    big_label, big_faces = big
    pairs = edge_pairs(graph, links)
    if len(pairs) < 2:
        return False
    source = numpy.array([pair[0] for pair in pairs.values()])
    target = numpy.array([pair[1] for pair in pairs.values()])
    rounded_source = numpy.round(source, 9)
    if (rounded_source == rounded_source[0]).all():
        return False
    if islands.signed_area(small_label, small_faces) * islands.signed_area(big_label, big_faces) <= 0:
        return False
    fit = similarity(source, target)
    if fit is None or fit[1] > FIT_ERROR * fit[2] * 2 or not SCALE_RANGE[0] <= abs(fit[0]) <= SCALE_RANGE[1]:
        return False
    loops = graph.loops_of(small_faces)
    candidate = moved(graph.uv[loops], fit[0], fit[3], fit[4])
    others = islands.near(big_label, big_faces, candidate)
    position = islands.position
    position[loops] = numpy.arange(len(loops))
    corners = candidate[position[graph.triangle_loops[islands.triangles_of(small_label, small_faces)]]]
    edge_a, edge_b = corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
    solid = numpy.abs(edge_a[:, 0] * edge_b[:, 1] - edge_a[:, 1] * edge_b[:, 0]) > TINY
    if any_overlap(corners[solid], others):
        return False
    graph.uv[loops] = candidate
    for loop, vertex in zip(loops.tolist(), graph.loop_vertex[loops].tolist()):
        if vertex in pairs:
            graph.uv[loop] = pairs[vertex][1]
    return True


def merge_small_islands(graph, minimum_share):
    total = float(graph.area.sum())
    if minimum_share <= 0 or total <= 0:
        return 0
    limit = minimum_share * total
    members = graph.members()
    areas = {label: float(graph.area[faces].sum()) for label, faces in members.items()}
    queue = [(area, label) for label, area in areas.items() if area < limit]
    heapq.heapify(queue)
    islands = Islands(graph)
    merged = 0
    while queue:
        area, label = heapq.heappop(queue)
        if label not in members or areas[label] != area:
            continue
        links_by_island = graph.boundary(members[label], label)
        ranked = sorted(links_by_island.items(), key=lambda item: -sum(float(graph.edge_length[edge]) for _, _, edge in item[1]))
        for neighbour, links in ranked:
            if attach(graph, islands, (label, members[label]), (neighbour, members[neighbour]), links):
                islands.merge(label, members[label], neighbour, members[neighbour])
                graph.labels[members[label]] = neighbour
                members[neighbour].extend(members.pop(label))
                areas[neighbour] += areas.pop(label)
                if areas[neighbour] < limit:
                    heapq.heappush(queue, (areas[neighbour], neighbour))
                merged += 1
                break
    return merged


def equalize_density(graphs):
    uv_total = sum(float(graph.triangle_uv_area().sum()) for graph in graphs)
    world_total = sum(float(graph.area.sum()) for graph in graphs)
    if uv_total <= TINY or world_total <= TINY:
        return 0
    target = (uv_total / world_total) ** 0.5
    scaled = 0
    for graph in graphs:
        uv_areas, world_areas = graph.island_uv_areas(), graph.island_world_areas()
        for label, faces in graph.members().items():
            if uv_areas[label] <= TINY or world_areas[label] <= TINY:
                continue
            factor = target / (uv_areas[label] / world_areas[label]) ** 0.5
            loops = graph.loops_of(faces)
            centre = graph.uv[loops].mean(axis=0)
            graph.uv[loops] = (graph.uv[loops] - centre) * factor + centre
            scaled += 1
    return scaled
