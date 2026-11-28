"""Limits of the fluvial terrain tool."""

from .limit_base import MEMORY, PHYSICAL, TIME, limit

LEAST_FLUVIAL_SIDE = limit("least_fluvial_side", 65, "cells", PHYSICAL,
                           "Below 65 cells a side no drainage network has room to branch, so Strahler orders and Hack's law say nothing.")
MAX_FLUVIAL_SIDE = limit("fluvial_side", 4_096, "cells", MEMORY,
                         "The model keeps about thirty grids of the full size; at 4096 cells a side that is 17 million cells and "
                         "about 4 GB, half the judge's memory.",
                         "a larger cell size for a larger domain")
LEAST_FLUVIAL_CELL = limit("least_fluvial_cell", 5.0, "m", PHYSICAL,
                           "Below about 5 m the hillslope processes, not stream power, shape the ground; the detail belongs to the "
                           "amplification stage.")
MAX_FLUVIAL_CELL = limit("fluvial_cell", 1_000.0, "m", PHYSICAL,
                         "Past 1 km a cell holds whole valleys, and its channel stands for a network the grid cannot show.")
MAX_UPLIFT_RATE = limit("uplift_rate", 0.02, "m/yr", PHYSICAL,
                        "The fastest measured rock uplift, in the Himalayan syntaxes and Taiwan, is about 10 mm/yr; 20 mm/yr leaves room.")
MAX_ERODIBILITY = limit("erodibility", 1e-3, "m^(1-2m)/yr", PHYSICAL,
                        "Stream-power erodibility spans about 1e-7 to 1e-4 over rock types (Stock and Montgomery 1999); 1e-3 leaves "
                        "room for very weak rock.")
LEAST_AREA_EXPONENT = limit("least_area_exponent", 0.2, "", PHYSICAL,
                            "River concavity m/n lies between about 0.35 and 0.65 (Kirby and Whipple 2012); below 0.2 profiles are "
                            "almost straight.")
MAX_AREA_EXPONENT = limit("area_exponent", 1.0, "", PHYSICAL,
                          "Above 1 the stream-power law makes profiles more concave than any river.")
MAX_DIFFUSIVITY = limit("hillslope_diffusivity", 1.0, "m^2/yr", PHYSICAL,
                        "Measured hillslope diffusivities are about 0.001 to 0.02 m^2/yr (Roering et al. 1999, Hurst et al. 2012); "
                        "1 m^2/yr is already far beyond soil creep.")
MAX_HILLSLOPE_GRADIENT = limit("hillslope_gradient", 3.0, "m/m", PHYSICAL,
                               "A gradient of 3 is 72 degrees; soil and rubble do not stand on steeper hillslopes.")
MAX_CHANNEL_AREA = limit("channel_area", 1e8, "m^2", PHYSICAL,
                         "Channels begin at source areas of 1e2 to 1e5 m^2 (Montgomery and Dietrich 1988); a head of 100 km^2 would "
                         "leave no network.")
MAX_LITHOLOGY_FACTOR = limit("lithology_factor", 100.0, "", PHYSICAL,
                             "Erodibility varies about a hundredfold between strong and weak rock in one range.")
MAX_LITHOLOGY_BANDS = limit("lithology_bands", 16, "bands", PHYSICAL,
                            "Sixteen kinds of rock in repeating bands is more than any mapped range shows at this scale.")
MAX_FLUVIAL_TILES = limit("fluvial_tiles", 16, "tiles per side", MEMORY,
                          "Each tile is one mesh object; 16 x 16 tiles of a 4096-cell grid are 256 objects of 66 000 vertices.")
MAX_FLUVIAL_LODS = limit("fluvial_lods", 4, "levels", TIME,
                         "Every level of detail decimates every tile again; four halvings take a tile to a sixteenth of its triangles.")
MAX_FLUVIAL_SIZE = limit("fluvial_size", 4_095.0, "km", PHYSICAL,
                         "The widest grid, 4096 cells of the largest cell size, 1 km; a range wider than that is a continent.")
