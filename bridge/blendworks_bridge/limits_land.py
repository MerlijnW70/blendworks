"""Limits of the distant land, forest, impostor and valley mist tools."""
from .limit_base import MEMORY, PHYSICAL, PROTOCOL, TIME, limit

LEAST_LAND_DISTANCE = limit("land_distance_min", 80_000.0, "m", PHYSICAL,
                            "Distant land reaches at least 80 km: from a 500 m hill the horizon lies 80 km away, so "
                            "land that ends sooner shows its edge.")
EARTH_RADIUS = 6_371_000.0
LEAST_PLANET_RADIUS = limit("planet_radius_min", 100_000.0, "m", PHYSICAL,
                            "A world smaller than 100 km across bends its horizon within a few kilometres; smaller "
                            "worlds are not landscapes.")
MAX_PLANET_RADIUS = limit("planet_radius", 100_000_000.0, "m", PHYSICAL,
                          "Far beyond any rocky planet (Earth 6371 km); a larger radius is a flat world.")
LEAST_LAND_DETAIL = limit("land_detail_min", 8, "vertices", PHYSICAL,
                          "Eight vertices across a ring's inner half size is the coarsest ring that still shows a hill.")
MAX_LAND_DETAIL = limit("land_detail", 512, "vertices", MEMORY,
                        "At 512 vertices across a ring's inner half size every ring holds about two million triangles, "
                        "the whole land budget.")
LEAST_BEHIND = limit("land_behind_min", 1.0, "", PHYSICAL, "1 keeps the spacing of the land in view on every side.")
MAX_BEHIND = limit("land_behind", 16.0, "", PHYSICAL,
                   "Land out of view needs only its silhouette for shadows and reflections; 16 times sparser keeps it.")
MAX_LAND_TRIANGLES = limit("land_triangles", 3_000_000, "triangles", MEMORY,
                           "Three million triangles take about 1.5 million vertices, under the mesh vertex limit, and "
                           "about 0.7 GB with the renderer's BVH (land_triangle_bytes), well inside an 8 GB machine.")
DEFAULT_LAND_TRIANGLES = 1_500_000
LAND_TRIANGLE_BYTES = limit("land_triangle_bytes", 240, "bytes", MEMORY,
                            "Per triangle of land: the mesh in Blender (positions, corners, edges, normals, UVs and "
                            "three attributes, about 110 bytes) and in Cycles (vertices, triangles, normals and BVH "
                            "nodes, about 130 bytes).")
MAX_LAND_MEMORY = limit("land_memory", MAX_LAND_TRIANGLES.plain() * LAND_TRIANGLE_BYTES.plain(), "bytes", MEMORY,
                        "The triangle budget times the bytes per triangle: what the largest land may hold.")
BORDER_TOLERANCE = limit("land_border_tolerance", 0.01, "m", PHYSICAL,
                         "Border heights of distant land are taken from the region's own surface; 1 cm covers the ray "
                         "casts a millimetre inside the border on slopes up to 85 degrees.")
MAX_RANGE_HEIGHT = limit("range_height", 6_000.0, "m", PHYSICAL,
                         "Mountain ranges rise at most about 6 km above the land at their feet (the Himalaya above "
                         "the Ganges plain).")
MAX_FOREST_TREES = limit("forest_trees", 200_000, "trees", MEMORY,
                         "Near trees are linked instances (about 300 bytes each) and impostor cards four vertices "
                         "each; 200 000 of them stay under 100 MB.")
MAX_FOREST_VARIANTS = limit("forest_variants", 12, "trees", TIME,
                            "Each variant is a whole tree that is grown, meshed, leafed and baked into an atlas, "
                            "several seconds each.")
MAX_IMPOSTOR_FRAMES = limit("impostor_frames", 16, "frames", MEMORY,
                            "A 16 by 16 atlas of views is 256 directions, 8 degrees apart over the upper hemisphere.")
MAX_IMPOSTOR_PIXELS = limit("impostor_pixels", 512, "px", MEMORY,
                            "Frame size; a 16 by 16 atlas of 512 px frames is 8192 px square, the image limit.")
LEAST_IMPOSTOR_PIXELS = limit("impostor_pixels_min", 16, "px", PHYSICAL,
                              "A view smaller than 16 px loses the crown's outline; cards that small are canopy.")
MAX_FOREST_BAND = limit("forest_band", 0.5, "", PHYSICAL,
                        "A switch band of half its distance each way already spans a factor of three in distance.")
MAX_MIST_CELLS = limit("mist_cells", 1024, "cells", MEMORY,
                       "The low-ground map is a float image of at most 1024 by 1024 cells (4 MB) and as many ray "
                       "casts.")
LEAST_MIST_CELLS = limit("mist_cells_min", 16, "cells", PHYSICAL,
                         "Fewer than 16 cells across cannot hold a valley.")
MAX_COVER_SHARE = limit("cover_share", 1.0, "", PHYSICAL, "A share of the land runs from 0 to 1.")
MAX_PROTOCOL_SPECIES = limit("forest_species", 6, "species", PROTOCOL,
                             "Blendworks grows six tree species: oak, birch, pine, willow, maple and olive.")
