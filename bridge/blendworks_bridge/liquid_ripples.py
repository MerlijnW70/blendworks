import math

import bpy
import numpy

from . import liquid_spectrum

DETAIL_SIZE = 8.0
DETAIL_RESOLUTION = 512
MESH_WAVES_PER_CELL = 4.0


def mesh_cutoff(cell):
    """Largest wave number the mesh carries: waves of at least four cells."""
    return 2.0 * math.pi / (MESH_WAVES_PER_CELL * cell)


def detail_tile(state, direction, cell, seed, size=DETAIL_SIZE, resolution=DETAIL_RESOLUTION):
    """The short waves the mesh cannot carry, as a periodic height tile for the bump."""
    low = mesh_cutoff(cell) if cell > 0.0 else 0.0
    return liquid_spectrum.synthesise(state, direction, resolution, size, seed + 101, band=(low, math.inf))


def tile_image(name, tile):
    image = bpy.data.images.get(name)
    if image is not None:
        bpy.data.images.remove(image)
    n = tile.resolution
    image = bpy.data.images.new(name, n, n, alpha=False, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    heights = tile.heights.astype(numpy.float32)
    pixels = numpy.ones((n, n, 4), dtype=numpy.float32)
    pixels[:, :, 0] = heights
    pixels[:, :, 1] = heights
    pixels[:, :, 2] = heights
    image.pixels.foreach_set(pixels.ravel())
    image.pack()
    return image


def ripples(name, state, direction, cell, seed, coordinates="world", uv_scale=(1.0, 1.0)):
    if state["hs"] <= 0.0:
        return None, None
    tile = detail_tile(state, direction, cell, seed)
    if tile.variance <= 0.0:
        return None, tile
    image = tile_image(name, tile)
    return {"image": image, "size": tile.size, "coordinates": coordinates, "uv_scale": uv_scale, "amplitude": 1.0}, tile


def slope_statistics(tile, direction):
    """Mean square slopes of a tile along and across the wind direction."""
    heading = math.radians(direction)
    along = tile.slope_x * math.sin(heading) + tile.slope_y * math.cos(heading)
    across = tile.slope_x * math.cos(heading) - tile.slope_y * math.sin(heading)
    return float(numpy.mean(along * along)), float(numpy.mean(across * across))
