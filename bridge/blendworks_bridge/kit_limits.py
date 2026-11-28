"""Data table of the limits of the modelling kit tools."""

from .limits import MEMORY, PHYSICAL, PROTOCOL, TIME, limit

MAX_PROFILE_POINTS = limit("profile_points", 512, "points", MEMORY,
                           "Points of one cross-section; a sweep makes profile points times path points vertices, and "
                           "512 times 4096 path points is about the mesh_vertices limit.")
MAX_PATH_POINTS = limit("path_points", 4_096, "points", MEMORY,
                        "Points of one path, sent inline or sampled from an exact circle or helix; with 512 profile "
                        "points a sweep along it stays near the mesh_vertices limit.")
MAX_SECTIONS = limit("loft_sections", 256, "sections", PROTOCOL, "Cross-sections of one loft sent inline as JSON.")
MAX_OUTLINE_POINTS = limit("outline_points", 4_096, "points", PROTOCOL, "Points of one flat outline sent inline as JSON.")
MAX_HOLES = limit("outline_holes", 64, "holes", PROTOCOL, "Hole outlines of one flat plate sent inline as JSON.")
MAX_SEGMENTS = limit("turn_segments", 512, "segments", PHYSICAL,
                     "Steps around a turned part; at 512 steps a chord leaves the true circle by less than 0.002 % of "
                     "the radius, so more steps add no visible roundness.")
MAX_TEETH = limit("gear_teeth", 400, "teeth", PHYSICAL,
                  "Teeth of one gear or sprocket; at 400 a tooth spans under one degree of the pitch circle and reads "
                  "as a knurl.")
MAX_INSTANCES = limit("instances", 20_000, "instances", TIME,
                      "Each copy is its own Blender object; past 20 000 objects the dependency graph update after "
                      "every later call slows down.", "scatter or ground_cover (instances drawn by the renderer)")
MAX_CHAIN_LINKS = limit("chain_links", 2_000, "links", TIME,
                        "Each link adds its plates, rollers and pins to the chain mesh one by one.")
MAX_QUERY_PAGE = limit("query_page", 1_000, "items", PROTOCOL, "Items one reply page lists; use offset for more.")
DEFAULT_QUERY_PAGE = 100
MAX_DATA_FILE_BYTES = limit("data_file_bytes", 256 * 1024 * 1024, "bytes", MEMORY,
                            "One JSON data file is read whole into memory and parsed.")
MAX_SIMPLE_CHECK_POINTS = limit("simple_check_points", 6_000, "points", TIME,
                                "The self-crossing check compares every edge with every other; past 6 000 points (36 "
                                "million pairs) it is skipped.")
MAX_DENTS = limit("dents", 2_000, "dents", TIME,
                  "Dents are pressed one at a time, each visiting the vertices within its reach.")
MAX_TREE_NODES = limit("tree_nodes", 50_000, "nodes", TIME,
                       "Skeleton nodes of one tree or L-system; growth, radii and the mesh walk every node, and 50 000 "
                       "is a large tree down to its twigs.")
MAX_TREE_POINTS = limit("tree_points", 50_000, "points", TIME,
                        "Attraction points of space colonization; every growth step searches them against the nodes.")
MAX_FRACTURE_PIECES = limit("fracture_pieces", 1_000, "pieces", TIME,
                            "Each piece is cut by exact planes and becomes its own object.")
MAX_CHIPS = limit("chips", 500, "chips", TIME, "Each chip is an exact plane cut of the whole solid.")
MAX_BLOB_POINTS = limit("blob_spheres", 256, "spheres", TIME,
                        "Every cell of the metaball field sums the spheres that reach it.")
MAX_ABRADE_ITERATIONS = limit("abrasion_passes", 500, "passes", TIME,
                              "Each pass smooths every vertex once and measures the volume.")
MAX_LSYSTEM_MODULES = limit("lsystem_modules", 1_000_000, "modules", MEMORY,
                            "Modules of a derived L-system word, each held as a Python tuple.")
