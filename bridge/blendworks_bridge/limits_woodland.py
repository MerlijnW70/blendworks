"""Woodland limits.

Limits of the woodland tool: stands, copses, variants, plants and the triangle and memory budgets."""
from .limit_base import MEMORY, PHYSICAL, PROTOCOL, TIME, limit

MAX_STANDS = limit("woodland_stands", 64, "stands", PROTOCOL, "Stands described inline in one woodland call.")
MAX_COPSES = limit("woodland_copses", 200, "copses", PHYSICAL,
                   "200 copses of 15 m radius cover about 14 hectares, a whole farmed valley; more belongs to a forest stand.")
LEAST_LIOCOURT_Q = limit("liocourt_q_min", 1.0, "", PHYSICAL,
                         "A quotient of 1 gives as many mature trees as young ones and saplings, an even-aged stand.")
MAX_LIOCOURT_Q = limit("liocourt_q", 3.0, "", PHYSICAL,
                       "Meyer (1952) found quotients of 1.2 to 2 per diameter class in balanced uneven-aged stands; "
                       "3 already leaves only one tree in fourteen mature.")
MAX_WOODLAND_VARIANTS = limit("woodland_variants", 6, "trees", TIME,
                              "Each variant is a tree grown, meshed and leaved (about 10 to 60 s); six per species and "
                              "class already hide the repetition among instances.")
MAX_UNDERSTOREY_VARIANTS = limit("understorey_variants", 32, "plants", TIME,
                                 "Ferns and herbs are built in code in well under a second each; 32 per kind is more "
                                 "than the eye separates.")
MAX_DENSITY_FACTOR = limit("woodland_density_factor", 10.0, "", PHYSICAL,
                            "Ten times the default densities packs shrubs crown to crown and herbs a dozen to the square "
                            "metre; denser cannot stand.")
MAX_RIM_WANDER = limit("rim_wander", 50.0, "m", PHYSICAL,
                       "Edges of woods and copses wander by metres to tens of metres around their mapped line.")
MAX_EDGE_ZONE = limit("edge_zone", 100.0, "m", PHYSICAL,
                      "Herb fringes, shrub mantles and transition zones of forest edges are metres to a few tens of "
                      "metres wide (docs/research/woodland.md); 100 m is already forest interior.")
WOODLAND_TRIANGLE_BYTES = limit("woodland_triangle_bytes", 720, "bytes", MEMORY,
                                "Per triangle of a plant variant, measured: 9.9 million variant triangles took 3.9 GB "
                                "resident after growing (the undo copy included) and 7.1 GB at the peak of a Cycles CPU "
                                "render, about 720 bytes per triangle.")
WOODLAND_INSTANCE_BYTES = limit("woodland_instance_bytes", 300, "bytes", MEMORY,
                                "Per instanced plant: its point, matrix and attributes in Blender and its object "
                                "instance in Cycles, as for the near trees of distant_forest.")
MAX_WOODLAND_TRIANGLES = limit("woodland_triangles", 8_000_000, "triangles", MEMORY,
                               "Eight million unique triangles take about 5.8 GB at their render peak "
                               "(woodland_triangle_bytes), the most an 8 GB machine can give the plants.")
DEFAULT_WOODLAND_TRIANGLES = 8_000_000
MAX_WOODLAND_PLANTS = limit("woodland_plants", 2_000_000, "plants", MEMORY,
                            "Two million instances take about 0.6 GB (woodland_instance_bytes).")
DEFAULT_WOODLAND_PLANTS = 400_000
MAX_WOODLAND_MEMORY = limit("woodland_memory", 6_000_000_000, "bytes", MEMORY,
                            "Six gigabytes of plants leave two of an 8 GB machine to Blender, the terrain and the render.")
DEFAULT_WOODLAND_MEMORY = 3_500_000_000
