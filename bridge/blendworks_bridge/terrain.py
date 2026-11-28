"""Terrain tile mesh: grid points, heights, rim and unfold."""

import numpy

from .edge_order import canonical_edges
from .noise_stack import stack_field


def grid_points(size, resolution, tile):
    steps = resolution - 1
    along_x = (tile[0] * steps + numpy.arange(resolution)) * (size[0] / steps)
    along_y = (tile[1] * steps + numpy.arange(resolution)) * (size[1] / steps)
    columns, rows = numpy.meshgrid(along_x, along_y)
    return columns.ravel(), rows.ravel()


def surface_heights(columns, rows, params, height, base_height):
    field = stack_field(numpy.stack([columns, rows, numpy.zeros_like(columns)], axis=1), params)
    return base_height + height * field


def rim_indices(resolution):
    steps = resolution - 1
    grid = numpy.arange(resolution * resolution).reshape(resolution, resolution)
    return numpy.concatenate([grid[0, :steps], grid[:steps, steps], grid[steps, steps:0:-1], grid[steps:0:-1, 0]])


def top_quads(resolution):
    grid = numpy.arange(resolution * resolution).reshape(resolution, resolution)
    return numpy.stack([grid[:-1, :-1].ravel(), grid[:-1, 1:].ravel(), grid[1:, 1:].ravel(), grid[1:, :-1].ravel()], axis=1)


def top_uvs(resolution, tile):
    steps = resolution - 1
    along_u = (tile[0] * steps + numpy.arange(resolution)) / steps
    along_v = (tile[1] * steps + numpy.arange(resolution)) / steps
    columns, rows = numpy.meshgrid(along_u, along_v)
    return numpy.stack([columns.ravel(), rows.ravel()], axis=1)


def rim_unfold(resolution, rim_uv, drop, size):
    steps = resolution - 1
    direction = numpy.zeros((len(rim_uv), 2))
    direction[:steps, 1] = -1.0
    direction[steps : 2 * steps, 0] = 1.0
    direction[2 * steps : 3 * steps, 1] = 1.0
    direction[3 * steps :, 0] = -1.0
    return rim_uv + direction * (drop[:, None] / numpy.array(size)[None, :])


class TileMesh:
    def __init__(self, columns, rows, heights, resolution, size, tile, floor):
        self.resolution = resolution
        self.points = numpy.stack([columns, rows, heights], axis=1)
        self.uv_top = top_uvs(resolution, tile)
        quads = top_quads(resolution)
        self.faces = [quads.ravel()]
        self.sizes = [numpy.full(len(quads), 4)]
        self.uvs = [self.uv_top[quads.ravel()]]
        self.smooth = [numpy.ones(len(quads), dtype=bool)]
        self.rim = None
        if floor is not None:
            self.add_skirt(size, floor)

    def add_skirt(self, size, floor):
        rim = rim_indices(self.resolution)
        count = len(rim)
        bottom = len(self.points) + numpy.arange(count)
        base = self.points[rim].copy()
        drop = base[:, 2] - floor
        base[:, 2] = floor
        self.points = numpy.concatenate([self.points, base])
        rim_uv = self.uv_top[rim]
        foot_uv = rim_unfold(self.resolution, rim_uv, drop, size)
        following = numpy.roll(numpy.arange(count), -1)
        walls = numpy.stack([rim, bottom, bottom[following], rim[following]], axis=1)
        wall_uvs = numpy.stack([rim_uv, foot_uv, foot_uv[following], rim_uv[following]], axis=1).reshape(-1, 2)
        shift = 1.0 + drop.max() / size[0] + 0.05
        self.faces += [walls.ravel(), bottom[::-1]]
        self.sizes += [numpy.full(count, 4), numpy.array([count])]
        self.uvs += [wall_uvs, (rim_uv + numpy.array([shift, 0.0]))[::-1]]
        self.smooth += [numpy.zeros(count, dtype=bool), numpy.zeros(1, dtype=bool)]
        self.rim = rim

    def build(self, mesh):
        mesh.clear_geometry()
        mesh.vertices.add(len(self.points))
        mesh.vertices.foreach_set("co", self.points.ravel())
        sizes = numpy.concatenate(self.sizes)
        mesh.loops.add(int(sizes.sum()))
        mesh.polygons.add(len(sizes))
        mesh.loops.foreach_set("vertex_index", numpy.concatenate(self.faces))
        mesh.polygons.foreach_set("loop_start", numpy.concatenate([[0], numpy.cumsum(sizes)[:-1]]))
        mesh.polygons.foreach_set("loop_total", sizes)
        mesh.polygons.foreach_set("use_smooth", numpy.concatenate(self.smooth))
        mesh.update(calc_edges=True)
        canonical_edges(mesh)
        layer = mesh.uv_layers.new(name="UVMap")
        layer.uv.foreach_set("vector", numpy.concatenate(self.uvs).ravel())
        if self.rim is not None:
            self.harden_rim(mesh)
        mesh.update()

    def harden_rim(self, mesh):
        on_rim = numpy.zeros(len(self.points), dtype=bool)
        on_rim[self.rim] = True
        pairs = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int64)
        mesh.edges.foreach_get("vertices", pairs)
        pairs = pairs.reshape(-1, 2)
        mesh.edges.foreach_set("use_edge_sharp", on_rim[pairs[:, 0]] & on_rim[pairs[:, 1]])
