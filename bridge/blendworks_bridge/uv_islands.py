import heapq

import numpy

SAME_UV = 1e-6
FIT_ERROR = 0.05
SCALE_RANGE = (0.2, 5.0)
OVERLAP_EPSILON = 1e-7
TINY = 1e-18
COMPLEX = numpy.array([1.0, 1j])


def triangles_overlap(triangle, others):
    if len(others) == 0:
        return False
    low, high = triangle.min(axis=0), triangle.max(axis=0)
    near = (others.max(axis=1) > low + OVERLAP_EPSILON).all(axis=1) & (others.min(axis=1) < high - OVERLAP_EPSILON).all(axis=1)
    others = others[near]
    if len(others) == 0:
        return False
    apart = numpy.zeros(len(others), dtype=bool)
    for index in range(3):
        edge = triangle[(index + 1) % 3] - triangle[index]
        axis = numpy.array([-edge[1], edge[0]]) / max(numpy.linalg.norm(edge), TINY)
        mine, theirs = triangle @ axis, others @ axis
        apart |= (theirs.min(axis=1) >= mine.max() - OVERLAP_EPSILON) | (theirs.max(axis=1) <= mine.min() + OVERLAP_EPSILON)
    for index in range(3):
        edge = others[:, (index + 1) % 3] - others[:, index]
        axis = numpy.stack([-edge[:, 1], edge[:, 0]], axis=1) / numpy.maximum(numpy.linalg.norm(edge, axis=1, keepdims=True), TINY)
        mine = triangle @ axis.T
        theirs = numpy.einsum("kjc,kc->kj", others, axis)
        apart |= (theirs.min(axis=1) >= mine.max(axis=0) - OVERLAP_EPSILON) | (theirs.max(axis=1) <= mine.min(axis=0) + OVERLAP_EPSILON)
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

    def continuous(self, first, second):
        for loop in (first, self.following(first)):
            partner = self.matching(first, second, self.loop_vertex[loop])
            if numpy.abs(self.uv[loop] - self.uv[partner]).max() > SAME_UV:
                return False
        return True

    def find_labels(self):
        parent = list(range(len(self.start)))

        def find(item):
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        for loops in self.edge_loops.values():
            if len(loops) == 2 and self.continuous(*loops):
                parent[find(int(self.face_of_loop[loops[0]]))] = find(int(self.face_of_loop[loops[1]]))
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
        found = {}
        for face in faces:
            for loop in range(int(self.start[face]), int(self.start[face] + self.total[face])):
                edge = int(self.loop_edge[loop])
                others = [item for item in self.edge_loops[edge] if item != loop]
                if self.seams[edge] or len(others) != 1:
                    continue
                neighbour = int(self.labels[self.face_of_loop[others[0]]])
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
    z = (source - source.mean(axis=0)) @ COMPLEX
    w = (target - target.mean(axis=0)) @ COMPLEX
    energy = float((numpy.abs(z) ** 2).sum())
    if energy < TINY:
        return None
    factor = complex((numpy.conj(z) * w).sum() / energy)
    error = float(numpy.abs(factor * z - w).max())
    return factor, error, float(numpy.abs(w).max())


def moved(points, factor, source, target):
    z = (points - source.mean(axis=0)) @ COMPLEX
    rotated = factor * z
    return numpy.stack([rotated.real, rotated.imag], axis=1) + target.mean(axis=0)


def attach(graph, small, big, links):
    pairs = edge_pairs(graph, links)
    if len(pairs) < 2:
        return False
    source = numpy.array([pair[0] for pair in pairs.values()])
    target = numpy.array([pair[1] for pair in pairs.values()])
    if len(numpy.unique(numpy.round(source, 9), axis=0)) < 2:
        return False
    if graph.signed_area(small) * graph.signed_area(big) <= 0:
        return False
    fit = similarity(source, target)
    if fit is None or fit[1] > FIT_ERROR * fit[2] * 2 or not SCALE_RANGE[0] <= abs(fit[0]) <= SCALE_RANGE[1]:
        return False
    loops = graph.loops_of(small)
    candidate = moved(graph.uv[loops], fit[0], source, target)
    where = {int(loop): index for index, loop in enumerate(loops)}
    wanted = numpy.nonzero(numpy.isin(graph.triangle_face, big))[0]
    others = graph.uv[graph.triangle_loops[wanted]]
    for triangle in numpy.nonzero(numpy.isin(graph.triangle_face, small))[0]:
        corners = candidate[[where[int(loop)] for loop in graph.triangle_loops[triangle]]]
        edge_a, edge_b = corners[1] - corners[0], corners[2] - corners[0]
        if abs(edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0]) > TINY and triangles_overlap(corners, others):
            return False
    graph.uv[loops] = candidate
    for index, loop in enumerate(loops):
        vertex = int(graph.loop_vertex[loop])
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
    merged = 0
    while queue:
        area, label = heapq.heappop(queue)
        if label not in members or areas[label] != area:
            continue
        links_by_island = graph.boundary(members[label], label)
        ranked = sorted(links_by_island.items(), key=lambda item: -sum(float(graph.edge_length[edge]) for _, _, edge in item[1]))
        for neighbour, links in ranked:
            if attach(graph, members[label], members[neighbour], links):
                graph.labels[members[label]] = neighbour
                members[neighbour] = members[neighbour] + members.pop(label)
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

