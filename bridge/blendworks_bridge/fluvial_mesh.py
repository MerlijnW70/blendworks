"""Terrain tiles of a fluvial run with drainage attributes."""

import bpy
import numpy

from .mesh_attributes import write_float_attribute
from .util import check_vertex_cap, link_object, require_free_name

ATTRIBUTES = {
    "height": "height in metres",
    "drainage_area": "drainage area, log10 of m^2",
    "channel": "1 on channels (drainage area at least the channel head area), else 0",
    "strahler": "Strahler order of the channel network, 0 off it",
    "lake_depth": "water depth of routed lakes in metres",
    "erosion": "height removed during the run in metres, negative where material was laid down",
}
"""Point attributes every tile carries, read by scatter masks, liquids and the later terrain stages."""


def tile_bounds(side, tiles):
    """Index ranges of the tiles along one side; neighbouring tiles share their edge row or column."""
    cuts = numpy.round(numpy.linspace(0, side - 1, tiles + 1)).astype(int)
    return [(int(cuts[index]), int(cuts[index + 1])) for index in range(tiles)]


def attribute_values(grids):
    return {
        "height": grids["height"],
        "drainage_area": numpy.log10(numpy.maximum(grids["drainage_area"], 1.0)),
        "channel": grids["channel"].astype(numpy.float64),
        "strahler": grids["strahler"].astype(numpy.float64),
        "lake_depth": grids["lake_depth"],
        "erosion": grids["erosion"],
    }


def surface_normals(heights, cell):
    """Unit normals of the whole height grid by central differences. Every tile takes its vertices' normals from
    here, so a vertex on a shared edge has the same normal in both tiles and the seam does not show."""
    rise_y, rise_x = numpy.gradient(heights, cell)
    normals = numpy.stack([-rise_x, -rise_y, numpy.ones_like(heights)], axis=-1)
    return normals / numpy.linalg.norm(normals, axis=-1, keepdims=True)


def grid_mesh(name, heights, cell, origin, extent, normals=None):
    """A quad mesh over a block of heights, vertices relative to origin, UVs in world metres over extent."""
    rows, columns = heights.shape
    check_vertex_cap(rows * columns)
    x = numpy.arange(columns) * cell
    y = numpy.arange(rows) * cell
    gx, gy = numpy.meshgrid(x, y)
    points = numpy.stack([gx.ravel(), gy.ravel(), heights.ravel()], axis=1)
    index = numpy.arange(rows * columns).reshape(rows, columns)
    quads = numpy.stack([index[:-1, :-1], index[:-1, 1:], index[1:, 1:], index[1:, :-1]], axis=-1).reshape(-1, 4)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(points))
    mesh.vertices.foreach_set("co", points.astype(numpy.float32).ravel())
    mesh.loops.add(quads.size)
    mesh.loops.foreach_set("vertex_index", quads.ravel().astype(numpy.int32))
    mesh.polygons.add(len(quads))
    mesh.polygons.foreach_set("loop_start", (numpy.arange(len(quads)) * 4).astype(numpy.int32))
    mesh.polygons.foreach_set("loop_total", numpy.full(len(quads), 4, dtype=numpy.int32))
    mesh.polygons.foreach_set("use_smooth", numpy.ones(len(quads), dtype=bool))
    world = points[:, :2] + numpy.asarray(origin)
    uv = mesh.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", (world[quads.ravel()] / extent).astype(numpy.float32).ravel())
    mesh.update()
    mesh.validate()
    if normals is not None:
        mesh.normals_split_custom_set_from_vertices(normals.reshape(-1, 3).astype(numpy.float32))
    return mesh


def build_tiles(ctx, name, grids, cell, tiles):
    """tiles x tiles mesh objects named name_i_j, placed at their world corners, with ATTRIBUTES as point data."""
    heights = grids["height"]
    side = heights.shape[0]
    extent = (side - 1) * cell
    values = attribute_values(grids)
    normals = surface_normals(heights, cell)
    bounds = tile_bounds(side, tiles)
    names = [f"{name}_{i}_{j}" for j in range(tiles) for i in range(tiles)]
    for tile_name in names:
        require_free_name(tile_name)
    built = []
    for j, (row_start, row_end) in enumerate(bounds):
        for i, (column_start, column_end) in enumerate(bounds):
            block = (slice(row_start, row_end + 1), slice(column_start, column_end + 1))
            origin = (column_start * cell, row_start * cell)
            tile_name = f"{name}_{i}_{j}"
            mesh = grid_mesh(tile_name, heights[block], cell, origin, extent, normals[block])
            for attribute in ATTRIBUTES:
                write_float_attribute(mesh, attribute, values[attribute][block].ravel())
            obj = link_object(ctx, tile_name, mesh)
            obj.location = (origin[0], origin[1], 0.0)
            built.append(obj.name)
    ctx.view_layer.update()
    return built


def save_grids(path, grids, cell):
    """Every output grid in one compressed numpy archive, with the cell size."""
    numpy.savez_compressed(path, cell=numpy.float64(cell), **{key: numpy.asarray(value) for key, value in grids.items()})
