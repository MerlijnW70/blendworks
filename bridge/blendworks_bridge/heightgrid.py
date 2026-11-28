"""Height grid tiles and tile sets for terrain."""

import math

import numpy

from .errors import bad_args, not_found
from .mesh_attributes import write_float_attribute
from .terrain import top_quads

COORDINATE_TOLERANCE = 1e-3
EDGE_TOLERANCE = 1e-6
NOT_A_GRID = "{name} is not a heightfield grid as heightfield builds it: {why}"


def grid_resolution(vertex_count):
    side = math.isqrt(vertex_count)
    if side >= 2 and side * side == vertex_count:
        return side, False
    side = math.isqrt(vertex_count + 8) - 2
    if side >= 2 and (side + 2) ** 2 == vertex_count + 8:
        return side, True
    return None, False


class Tile:
    def __init__(self, obj):
        self.obj = obj
        mesh = obj.data
        count = len(mesh.vertices)
        resolution, skirt = grid_resolution(count)
        if resolution is None:
            raise bad_args(NOT_A_GRID.format(name=obj.name, why=f"{count} vertices is neither n*n nor n*n plus a skirt of 4*(n-1)"))
        self.resolution = resolution
        self.skirt = skirt
        quads = (resolution - 1) ** 2
        expected_faces = quads + (4 * (resolution - 1) + 1 if skirt else 0)
        if len(mesh.polygons) != expected_faces:
            raise bad_args(NOT_A_GRID.format(name=obj.name, why=f"{len(mesh.polygons)} faces, a {resolution} x {resolution} grid has {expected_faces}"))
        corners = numpy.empty(len(mesh.loops), dtype=numpy.int64)
        mesh.loops.foreach_get("vertex_index", corners)
        if len(corners) < quads * 4 or not numpy.array_equal(corners[: quads * 4], top_quads(resolution).ravel()):
            raise bad_args(NOT_A_GRID.format(name=obj.name, why="its top faces are not the row-major quads of the grid"))
        local = numpy.empty(count * 3)
        mesh.vertices.foreach_get("co", local)
        self.local = local.reshape(count, 3)
        matrix = numpy.array(obj.matrix_world)
        linear = matrix[:3, :3]
        if not numpy.allclose(linear, numpy.diag(numpy.diag(linear)), atol=1e-9) or numpy.any(numpy.diag(linear) <= 0.0):
            raise bad_args(NOT_A_GRID.format(name=obj.name, why="its transform is rotated or flipped; only a move and a positive scale are allowed"))
        self.scale = numpy.diag(linear).copy()
        self.shift = matrix[:3, 3].copy()
        top = self.local[: resolution**2]
        world_x = (top[:, 0] * self.scale[0] + self.shift[0]).reshape(resolution, resolution)
        world_y = (top[:, 1] * self.scale[1] + self.shift[1]).reshape(resolution, resolution)
        self.origin = (float(world_x[0, 0]), float(world_y[0, 0]))
        self.spacing = (float(world_x[0, 1] - world_x[0, 0]), float(world_y[1, 0] - world_y[0, 0]))
        steps = numpy.arange(resolution)
        straight = numpy.abs(world_x - (self.origin[0] + steps * self.spacing[0])[None, :]).max() if self.spacing[0] > 0 else math.inf
        level = numpy.abs(world_y - (self.origin[1] + steps * self.spacing[1])[:, None]).max() if self.spacing[1] > 0 else math.inf
        if max(straight, level) > COORDINATE_TOLERANCE * min(self.spacing if min(self.spacing) > 0 else (1.0, 1.0)):
            raise bad_args(NOT_A_GRID.format(name=obj.name, why="its vertices are not on a regular grid of rows along x"))
        self.heights = (top[:, 2] * self.scale[2] + self.shift[2]).reshape(resolution, resolution)

    def weights(self, mask):
        resolution = self.resolution
        if mask is None:
            return numpy.ones((resolution, resolution))
        values = numpy.zeros(resolution**2)
        group = self.obj.vertex_groups.get(mask)
        attribute = self.obj.data.attributes.get(mask)
        if group is not None:
            for vertex in self.obj.data.vertices[: resolution**2]:
                for assignment in vertex.groups:
                    if assignment.group == group.index:
                        values[vertex.index] = assignment.weight
        elif attribute is not None and attribute.data_type == "FLOAT" and attribute.domain == "POINT":
            found = numpy.empty(len(attribute.data))
            attribute.data.foreach_get("value", found)
            values = found[: resolution**2]
        else:
            raise not_found(f"{self.obj.name} has no vertex group or float point attribute named {mask}")
        return numpy.clip(values, 0.0, 1.0).reshape(resolution, resolution)

    def store(self, heights):
        self.local[: self.resolution**2, 2] = ((heights - self.shift[2]) / self.scale[2]).ravel()
        self.obj.data.vertices.foreach_set("co", self.local.ravel())
        self.obj.data.update()

    def write_changes(self, erosion, deposition):
        total = len(self.obj.data.vertices)
        for name, values in (("erosion", erosion), ("deposition", deposition)):
            padded = numpy.zeros(total)
            padded[: self.resolution**2] = values.ravel()
            write_float_attribute(self.obj.data, name, padded)


class TileSet:
    def __init__(self, objects):
        self.tiles = [Tile(obj) for obj in objects]
        first = self.tiles[0]
        self.resolution = first.resolution
        self.spacing = first.spacing
        for tile in self.tiles[1:]:
            if tile.resolution != first.resolution or not numpy.allclose(tile.spacing, first.spacing, rtol=1e-6):
                raise bad_args(f"{tile.obj.name} and {first.obj.name} differ in resolution or spacing; tiles eroded together must match")
        steps = self.resolution - 1
        extent = (steps * self.spacing[0], steps * self.spacing[1])
        base = (min(tile.origin[0] for tile in self.tiles), min(tile.origin[1] for tile in self.tiles))
        self.places = {}
        for tile in self.tiles:
            column = (tile.origin[0] - base[0]) / extent[0]
            row = (tile.origin[1] - base[1]) / extent[1]
            if abs(column - round(column)) > 1e-4 or abs(row - round(row)) > 1e-4:
                raise bad_args(f"{tile.obj.name} does not sit on the tile lattice of {first.obj.name}; neighbouring tiles must share whole edges")
            place = (int(round(row)), int(round(column)))
            if place in self.places:
                raise bad_args(f"{tile.obj.name} and {self.places[place].obj.name} cover the same place")
            self.places[place] = tile
        rows = 1 + max(place[0] for place in self.places)
        columns = 1 + max(place[1] for place in self.places)
        if len(self.places) != rows * columns:
            raise bad_args("the tiles do not form a complete rectangle; add the missing tiles or erode fewer")
        self.shape = (rows * steps + 1, columns * steps + 1)

    def window(self, place):
        steps = self.resolution - 1
        return slice(place[0] * steps, place[0] * steps + self.resolution), slice(place[1] * steps, place[1] * steps + self.resolution)

    def assemble(self, fields):
        combined = numpy.zeros(self.shape)
        seen = numpy.zeros(self.shape, dtype=bool)
        for place, tile in self.places.items():
            window = self.window(place)
            values = fields(tile)
            overlap = seen[window]
            if overlap.any() and numpy.abs(combined[window][overlap] - values[overlap]).max() > EDGE_TOLERANCE:
                raise bad_args(f"{tile.obj.name} disagrees with a neighbour along a shared edge by more than {EDGE_TOLERANCE} m; tiles must come from one heightfield")
            combined[window] = numpy.where(overlap, combined[window], values)
            seen[window] = True
        return combined

    def heights(self):
        return self.assemble(lambda tile: tile.heights)

    def free_weights(self, mask):
        weights = numpy.zeros(self.shape)
        for place, tile in self.places.items():
            window = self.window(place)
            weights[window] = numpy.maximum(weights[window], tile.weights(mask))
        weights[0, :] = weights[-1, :] = 0.0
        weights[:, 0] = weights[:, -1] = 0.0
        return weights

    def write(self, before, after):
        change = after - before
        for place, tile in self.places.items():
            window = self.window(place)
            tile.store(after[window])
            tile.write_changes(numpy.maximum(-change[window], 0.0), numpy.maximum(change[window], 0.0))
