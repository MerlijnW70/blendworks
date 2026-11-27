"""Named limits of the material, mesh, render, rig and weather tools (commands m to z)."""
from .limit_base import BLENDER, MEMORY, PHYSICAL, PROTOCOL, TIME, limit

WINDING = limit("winding", 36_000.0, "deg", PHYSICAL,
                "An angle that may wind round, such as a screw, a twist along a path, a helix start or a dial's range: "
                "100 turns, more than any part winds; the vertex limit still caps the mesh it makes.")
MAX_INDICES = limit("listed_indices", 200_000, "indices", PROTOCOL,
                    "Face, edge or vertex indices sent inline as JSON; larger selections go by facing, box or "
                    "material, or take the whole mesh.")
MAX_SCALE_FACTOR = limit("scale_factor", 10_000.0, "", PHYSICAL,
                         "A scale factor of an object, a copy, a profile or a texture: ten thousandfold turns a "
                         "millimetre part into a 10 m one, or a 1 m tile into a 10 km one; anything larger is built "
                         "at its own size.")
SMALLEST_SCALE_FACTOR = limit("smallest_scale_factor", 0.0001, "", PHYSICAL,
                              "The smallest scale factor of a copy or a texture: a 1 m source shrinks to 0.1 mm, "
                              "below a pixel in any view.")
PAIR = limit("pair", 2, "items", PHYSICAL,
             "A path, a sequence or a set to combine needs a start and an end: at least two points, sections, wheels, "
             "copies, steps or objects.")
FEWEST_SIDES = limit("fewest_sides", 3, "points", PHYSICAL,
                     "A ring or a closed outline needs at least three points to enclose an area.")
ICO_SUBDIVISIONS = limit("ico_subdivisions", 7, "levels", MEMORY,
                         "Each level quadruples the faces of an icosphere; level 7 has 327 680 faces, rounder than "
                         "any sphere needs.")
EMISSION_STRENGTH = limit("emission_strength", 1_000.0, "", PHYSICAL,
                          "Emission strength of a surface; 1000 outshines any lamp a scene shows beside daylight (a "
                          "sun of strength 3 to 10).")
SCREW_STEPS = limit("screw_steps", 10_000, "steps", BLENDER,
                    "Blender's screw modifier takes at most 10 000 steps per turn and 10 000 turns.")
FEWEST_SPLIT_CORNERS = limit("fewest_split_corners", 4, "corners", BLENDER,
                             "Blender triangulates only faces of four or more corners; a triangle needs no split.")
NORMAL_WEIGHT = limit("normal_weight", 100, "", BLENDER, "Blender's weighted normal strength runs from 1 to 100.")
NORMAL_WEIGHT_THRESHOLD = limit("normal_weight_threshold", 10.0, "", BLENDER,
                                "Blender's weighted normal threshold runs from 0 to 10.")
BEVEL_SEGMENTS = limit("bevel_segments", 100, "segments", MEMORY,
                       "Each segment adds a row of faces along every bevelled edge, so bevel checks the result against "
                       "mesh_vertices first; 100 segments make a round no "
                       "render tells from a true arc.")
THICKNESS_CLAMP = limit("thickness_clamp", 100.0, "", BLENDER, "Blender's solidify clamp factor runs from 0 to 100.")
SUBDIVISION_LEVELS = limit("subdivision_levels", 6, "levels", BLENDER,
                           "Blender subdivides at most 6 levels in a modifier; each level quadruples the faces.")
SMALLEST_TEXTURE_FEATURE = limit("smallest_texture_feature", 0.0001, "m", PHYSICAL,
                                 "0.1 mm: finer texture features than this show in no render short of a macro shot.")
TEXTURE_FREQUENCY = limit("texture_frequency", 10_000.0, "1/m", PHYSICAL,
                          "Features per metre of a procedural texture; 10 000 per metre is 0.1 mm, the "
                          "smallest_texture_feature.")
TEXTURE_DEPTH = limit("texture_depth", 30, "levels", BLENDER,
                      "Blender's built-in noise textures take at most 30 detail levels.")
TEXTURE_INTENSITY = limit("texture_intensity", 2.0, "", BLENDER,
                          "Blender clamps a built-in texture's brightness to 0..2.")
TEXTURE_CONTRAST = limit("texture_contrast", 5.0, "", BLENDER, "Blender clamps a built-in texture's contrast to 0..5.")
OCTAVES = limit("octaves", 12, "octaves", TIME,
                "Each octave evaluates the noise once more at every point; at lacunarity 2 the twelfth octave is "
                "2048 times finer than the first, finer than the vertex spacing of any mesh it displaces.")
SMALLEST_LACUNARITY = limit("smallest_lacunarity", 1.0, "", PHYSICAL,
                            "Each octave is at least as fine as the one before; below 1 the octaves would grow "
                            "coarser.")
LACUNARITY = limit("lacunarity", 8.0, "", PHYSICAL,
                   "Past a frequency ratio of 8 the octaves lie so far apart in size that the sum shows separate "
                   "layers instead of one fractal.")
SMALLEST_PREVIEW_RESOLUTION = limit("smallest_preview_resolution", 64, "px", PHYSICAL,
                                    "Below 64 px a preview shows too little of the model to judge.")
BONE_INFLUENCES = limit("bone_influences", 8, "bones", PROTOCOL,
                        "glTF and game engines skin a vertex with at most 8 bones (two sets of four).")
SMOOTHING_PASSES = limit("smoothing_passes", 50, "passes", TIME,
                         "Each pass visits every edge of the mesh once; 50 passes spread a weight across a whole "
                         "limb.")
RIGID_PARTS = limit("rigid_parts", 256, "parts", PROTOCOL, "Rigid parts listed inline in one skin_bind call.")
SEARCH_SECONDS = limit("search_seconds", 300.0, "s", TIME,
                       "A packing or fitting search stops after this many seconds, well inside the longest call the "
                       "MCP server waits for.")
SHORTEST_SEARCH_SECONDS = limit("shortest_search_seconds", 1.0, "s", TIME,
                                "A search needs about a second for its first trial.")
EDGE_CUTS = limit("edge_cuts", 10, "cuts", MEMORY,
                  "Each cut multiplies the faces of a quad by (cuts + 1) squared, so ten cuts make 121 of one; the "
                  "mesh_vertices check still refuses a result that is too large.")
VARIATION = limit("variation", 0.95, "", PHYSICAL,
                  "A seeded change of a size or length, up to this share either way; at 100 % a varied size would "
                  "reach zero.")
SPACING_JITTER = limit("spacing_jitter", 0.49, "", PHYSICAL,
                       "A shift of up to this share of the even spacing keeps every member between its neighbours; "
                       "at half the spacing two would meet.")
ORGAN_INDEX = limit("organ_index", 1_000_000, "", PHYSICAL,
                    "Index of the first organ of a phyllotaxis; a sunflower head holds a few thousand florets, so a "
                    "million covers any part of any spiral.")
PROFILE_SEGMENTS = limit("profile_segments", 256, "segments", MEMORY,
                         "Segments of a preset cross-section: a rounded rectangle with 256 per corner already has "
                         "about 1000 points, twice profile_points, which a sweep along a full path would build before "
                         "the vertex check.")
CORNER_SEGMENTS = limit("corner_segments", 64, "segments", PHYSICAL,
                        "64 segments round a corner of up to half a turn to within 0.03 % of its radius; more add no "
                        "visible roundness.")
FEWEST_TEETH = limit("fewest_teeth", 6, "teeth", PHYSICAL,
                     "Below six teeth the involute flanks undercut away most of each tooth.")
SMALLEST_PRESSURE_ANGLE = limit("smallest_pressure_angle", 5.0, "deg", PHYSICAL,
                                "Standard gears are cut at 14.5 to 25 degrees; 5 degrees is far below any of them.")
PRESSURE_ANGLE = limit("pressure_angle", 35.0, "deg", PHYSICAL,
                       "Gears are cut at 14.5 to 25 degrees; above 35 the teeth come to a point below the tip "
                       "circle.")
FLANK_SAMPLES = limit("flank_samples", 24, "points", PHYSICAL,
                      "24 points draw an involute flank or a roller seat smoother than any render resolves.")
CHAIN_WHEELS = limit("chain_wheels", 16, "wheels", PROTOCOL,
                     "Wheels of one chain drive listed inline; real drives have two to a handful.")
DIAL_MARKS = limit("dial_marks", 3_600, "marks", TIME,
                   "Each mark is a cutter solid joined into one boolean; 3600 marks divide a dial into tenths of a "
                   "degree.")
MARK_CLASSES = limit("mark_classes", 16, "classes", PROTOCOL,
                     "Mark classes of one scale listed inline; dials use two to four (minor, half, major).")
SMALLEST_WHORL_EXPANSION = limit("smallest_whorl_expansion", 1.05, "", PHYSICAL,
                                 "Raup's W: below 1.05 a shell barely widens and needs hundreds of whorls to grow.")
WHORL_EXPANSION = limit("whorl_expansion", 100.0, "", PHYSICAL,
                        "Raup's W: coiled snails, ammonites and the nautilus lie between 1.1 and 10; 100 reaches the "
                        "flaring forms of limpets and ears.")
SMALLEST_CURVE_DISTANCE = limit("smallest_curve_distance", 0.01, "", PHYSICAL,
                                "Raup's D: below 0.01 the generating curve touches the axis and the whorls fuse "
                                "into one solid column.")
CURVE_DISTANCE = limit("curve_distance", 0.95, "", PHYSICAL,
                       "Raup's D: above 0.95 the generating curve shrinks to a thin sliver far from the axis.")
WHORL_TRANSLATION = limit("whorl_translation", 20.0, "", PHYSICAL,
                          "Raup's T: tall spires reach about 10; 20 leaves room for needle-like towers.")
WHORLS = limit("whorls", 24.0, "turns", PHYSICAL,
               "The most whorled real shells, the turritellids, have about 20 whorls; the path_points limit still caps "
               "whorls times steps.")
ASPECT_RATIO = limit("aspect_ratio", 20.0, "", PHYSICAL,
                     "An ellipse more than 20 times longer than wide reads as a slit.")
SMALLEST_ASPECT_RATIO = limit("smallest_aspect_ratio", 0.05, "", PHYSICAL,
                              "The inverse of aspect_ratio: an ellipse more than 20 times wider than high reads as a "
                              "slit.")
FEWEST_ROUND_STEPS = limit("fewest_round_steps", 8, "steps", PHYSICAL,
                           "A circle, an ellipse or a whorl drawn with fewer than 8 steps reads as a polygon.")
RIBS = limit("ribs", 64, "ribs", PHYSICAL,
             "Ribbed shells carry at most a few dozen ribs per whorl or ridges around the aperture.")
RELIEF_SHARE = limit("relief_share", 0.5, "", PHYSICAL,
                     "A rib, ridge or bark relief deeper than half the local size (aperture or branch radius) would "
                     "fold the wall over itself.")
LIP_FLARE = limit("lip_flare", 2.0, "", PHYSICAL,
                  "A lip that flares out more than twice the aperture size reads as a separate fan.")
LIP_THICKENING = limit("lip_thickening", 4.0, "", PHYSICAL,
                       "A rim more than five times the wall thickness closes the aperture of a small shell.")
SHORTEST_LIP = limit("shortest_lip", 0.02, "turns", PHYSICAL,
                     "A lip shorter than 2 % of a whorl spans less than one ring at the default 48 steps.")
BUMP_DEPTH = limit("bump_depth", 50.0, "mm", PHYSICAL,
                   "Bump mapping fakes relief only a few centimetres deep before the shading breaks up; deeper "
                   "relief is real geometry.", "noise_displace (displaces the mesh in metres)")
VEIN_PAIRS = limit("vein_pairs", 40, "pairs", PHYSICAL,
                   "Leaves carry up to about 30 pairs of lateral veins (beech, hornbeam, chestnut).")
FEWEST_VEIN_PAIRS = limit("fewest_vein_pairs", 2, "pairs", PHYSICAL,
                          "A blade with fewer than two vein pairs shows its midrib only, not a leaf.")
NEEDLES = limit("needles", 64, "needles", PHYSICAL,
                "More than 64 needles on one card blur into a solid blade at the size a card is seen.")
FEWEST_NEEDLES = limit("fewest_needles", 3, "needles", PHYSICAL, "A tuft needs three needles to read as a fan.")
WAVE_DISTORTION = limit("wave_distortion", 20.0, "", PHYSICAL,
                        "Past a distortion of 20 a wave texture's rings or bands tear into plain noise.")
TROPISM_WEIGHT = limit("tropism_weight", 4.0, "", PHYSICAL,
                       "A tropism vector of length 4 already outweighs the unit growth direction fourfold; longer "
                       "ones point every step straight along it.")
BEND_RATE = limit("bend_rate", 20.0, "rad/m", PHYSICAL,
                  "A bend of 20 radians per metre turns a twig tip a full circle within 30 cm; faster bends no "
                  "longer read as growth.")
SIZE_EXPONENT = limit("size_exponent", 4.0, "", PHYSICAL,
                      "An exponent of a size ratio: at 4 a branch half as thick already bends or shrinks 16 times "
                      "as much; more makes every thin twig limp.")
BRANCH_ORDERS = limit("branch_orders", 8, "orders", PHYSICAL,
                      "Trees branch about six orders deep from trunk to twig; 8 covers every species.")
STEM_LEVELS = limit("stem_levels", 4, "levels", PHYSICAL,
                    "Weber and Penn build a tree from at most four stem levels, trunk to twigs; leaves come after.")
STEM_CHILDREN = limit("stem_children", 200, "branches", PHYSICAL,
                      "A stem carries at most a couple of hundred side branches; max_nodes caps the whole tree.")
LENGTH_RATIO = limit("length_ratio", 2.0, "", PHYSICAL,
                     "A child more than twice as long as its parent no longer reads as a branch of it.")
WHORL_BRANCHES = limit("whorl_branches", 12, "branches", PHYSICAL,
                       "Conifers set at most about a dozen branches in one whorl.")
STEM_SEGMENTS = limit("stem_segments", 200, "nodes", PHYSICAL,
                      "200 nodes bend one stem more smoothly than any render shows; max_nodes caps the whole tree.")
SPECIFIC_STIFFNESS = limit("specific_stiffness", 1e12, "m", PHYSICAL,
                           "E / (rho g) of green wood is about 1e6 m and of steel about 3e6 m; 1e12 is rigid at any "
                           "tree size, so nothing sags.")
SMALLEST_PIPE_EXPONENT = limit("smallest_pipe_exponent", 1.8, "", PHYSICAL,
                               "Measured trees follow the pipe model with exponents from about 1.8 to 3; 2 is "
                               "Leonardo's rule.")
PIPE_EXPONENT = limit("pipe_exponent", 3.0, "", PHYSICAL,
                      "Measured trees follow the pipe model with exponents from about 1.8 to 3; 3 is Murray's "
                      "law for vessels.")
PREVIEW_BEVEL_RESOLUTION = limit("preview_bevel_resolution", 8, "segments", MEMORY,
                                 "The preview curve bevels every skeleton node; at 8 a tree of 50 000 nodes "
                                 "evaluates to near the mesh_vertices limit.")
LINEAR_DENSITY = limit("linear_density", 1_000.0, "1/m", PHYSICAL,
                       "Leaves, needles or ring segments per metre: 1000 puts one every millimetre, denser than "
                       "needles on a twig; the instance and vertex limits cap the result.")
TIP_LEAVES = limit("tip_leaves", 12, "leaves", PHYSICAL,
                   "A twig tip carries at most about a dozen leaves, as the whorl of a horse chestnut.")
TIP_SPRAYS = limit("tip_sprays", 8, "clusters", PHYSICAL,
                   "At most about eight shoots fan out of one twig tip; more merge into one ball of leaves.")
CLUSTER_LEAVES = limit("cluster_leaves", 80, "leaves", PHYSICAL,
                       "One spray carries at most about 80 leaves, as a conifer shoot drawn as needle cards.")
SPRAY_FORKS = limit("spray_forks", 8, "twigs", PHYSICAL,
                    "A leaf spray branches into at most about eight side twigs before it reads as a branch.")
LEAF_SHAPES = limit("leaf_shapes", 6, "shapes", PHYSICAL,
                    "The leaf preset draws a species' outline in at most six variants.")
CLUSTER_VARIANTS = limit("cluster_variants", 64, "meshes", MEMORY,
                         "Each variant is its own cluster mesh; 64 hide any repeat in a crown.")
HUE_SHIFT = limit("hue_shift", 0.2, "", PHYSICAL,
                  "Leaves of one tree vary in hue by at most a fifth of the colour circle either way; more turns "
                  "green leaves blue or red.")
FEWEST_BRANCH_SIDES = limit("fewest_branch_sides", 5, "segments", PHYSICAL,
                            "A branch drawn with fewer than five sides shows as a prism.")
RINGS_BETWEEN_NODES = limit("rings_between_nodes", 32, "rings", PHYSICAL,
                            "Rings sit about one edge apart; 32 between two skeleton nodes follow any bend, and the "
                            "vertex check caps the mesh.")
SWELLING = limit("swelling", 4.0, "", PHYSICAL,
                 "A trunk base, root or branch collar swells to at most five times its own radius, as the buttresses "
                 "of tropical trees.")
FEWEST_TRIANGLES = limit("fewest_triangles", 100, "triangles", PHYSICAL,
                         "Below 100 triangles a tree is a handful of prisms; a card does better.")
TRIANGLE_BUDGET = limit("triangle_budget", 2_000_000, "triangles", MEMORY,
                        "2 million triangles hold about 1 million vertices, half the mesh_vertices limit, leaving room "
                        "for the junction work.")
RELATIVE_WEIGHT = limit("relative_weight", 1_000_000.0, "", PHYSICAL,
                        "Weights compare up to a million to one; a source rarer than that never shows among the "
                        "instances one call places.")
LISTED_SOURCES = limit("listed_sources", 64, "meshes", PROTOCOL,
                       "Source meshes listed inline in one scatter; each is placed in its own pass.")
POWER_EXPONENT = limit("power_exponent", 8.0, "", PHYSICAL,
                       "Power-law size spectra in nature have exponents from about -1 to -4; at -8 almost every "
                       "instance takes the smallest size.")
TWILIGHT_DEPTH = limit("twilight_depth", 20.0, "deg", PHYSICAL,
                       "Twilight ends when the sun is 18 degrees below the horizon; 20 covers all of it.")
DATE_LENGTH = limit("date_length", 10, "characters", PROTOCOL, "A date written YYYY-MM-DD.")
TIME_LENGTH = limit("time_length", 12, "characters", PROTOCOL, "A clock time written HH:MM:SS.sss.")
UTC_OFFSET = limit("utc_offset", 14.0, "h", PHYSICAL, "Time zones run from UTC-12 to UTC+14.")
SKY_ALTITUDE = limit("sky_altitude", 60_000.0, "m", PHYSICAL,
                     "Balloons and high aircraft fly below about 40 km; at 60 km the sky above is black.")
ATMOSPHERE_DENSITY = limit("atmosphere_density", 10.0, "", PHYSICAL,
                           "1 is the standard atmosphere; ten times its air, dust or ozone already turns the sky "
                           "grey, and thicker haze is weather's job.")
SMALLEST_SUN_SIZE = limit("smallest_sun_size", 0.05, "deg", PHYSICAL,
                          "The sun is 0.53 degrees wide; at a tenth of that a shadow 10 m behind its edge blurs by "
                          "under 1 cm, sharper than any real sun shadow.")
SUN_SIZE = limit("sun_size", 10.0, "deg", PHYSICAL,
                 "A sun disc twenty times its true width reads as a lamp, not the sun.")
SUN_INTENSITY = limit("sun_intensity", 10.0, "", PHYSICAL,
                      "Ten times the physical sun disc already overexposes any shot by several stops.")
RAIN_RATE = limit("rain_rate", 100.0, "mm/h", PHYSICAL,
                  "Cloudbursts reach about 100 mm/h; the streak count saturates well before.")
MAP_STRENGTH = limit("map_strength", 10.0, "", PHYSICAL,
                     "A normal or height map at more than ten times its authored strength tilts the shading normals "
                     "past the horizon and breaks the surface up.")
NODE_INPUTS = limit("node_inputs", 64, "inputs", PROTOCOL, "Input values set inline on one node.")
NODE_SETTINGS = limit("node_settings", 16, "settings", PROTOCOL, "Settings set inline on one node.")
VACUUM_IOR = limit("vacuum_ior", 1.0, "", PHYSICAL, "Nothing refracts less than vacuum, index 1.")
INDEX_OF_REFRACTION = limit("index_of_refraction", 4.0, "", PHYSICAL,
                            "Diamond refracts at 2.42 and germanium at about 4, the highest of common materials.")
ATTENUATION = limit("attenuation", 1_000_000.0, "1/m", PHYSICAL,
                    "A coefficient of a million per metre stops light within a micrometre: opaque at any size.")
CONCENTRATION = limit("concentration", 100.0, "", PHYSICAL,
                      "A hundredfold concentrate of any liquid preset is already opaque within a millimetre.")
SMALLEST_GLOW_TEMPERATURE = limit("smallest_glow_temperature", 400.0, "degC", PHYSICAL,
                                  "Below 400 degrees Celsius lava and metal no longer glow; they start to show red "
                                  "near 525 (the Draper point).")
GLOW_TEMPERATURE = limit("glow_temperature", 3_000.0, "degC", PHYSICAL,
                         "Molten metals pour below about 3000 degrees Celsius (iron 1538, platinum 1768).")
FINAL_RESOLUTION = limit("final_resolution", 4_096, "px", MEMORY,
                         "A 4096 px square frame with its float passes and denoiser buffers takes about 1 GB, the "
                         "pixel guard.")
SMALLEST_RENDER_SIZE = limit("smallest_render_size", 16, "px", PHYSICAL,
                             "Below 16 px a frame shows nothing to judge.")
FINAL_SAMPLES = limit("final_samples", 65_536, "samples", TIME,
                      "Cycles stops converging visibly long before 65 536 samples a pixel; the time limit ends a "
                      "render first.")
RENDER_SECONDS = limit("render_seconds", 600.0, "s", TIME,
                       "The render call's default timeout of 900 s less 300 s for scene sync, denoising and writing.")
SHORTEST_RENDER_SECONDS = limit("shortest_render_seconds", 0.01, "s", TIME,
                                "A budget under 10 ms ends before Cycles finishes its first sample pass.")
SHUTTER_FRAMES = limit("shutter_frames", 10.0, "frames", PHYSICAL,
                       "A shutter open for ten frames already smears a moving object into a streak; film shutters "
                       "stay below one frame.")
SHORTEST_SHUTTER_FRAMES = limit("shortest_shutter_frames", 0.01, "frames", PHYSICAL,
                                "Below a hundredth of a frame motion blur stays under a pixel for all but the fastest "
                                "objects.")
UV_MARGIN = limit("uv_margin", 1.0, "", BLENDER,
                  "Space between islands as a share of the UV square; Blender's unwrap, smart project and pack take "
                  "margins up to 1.")
PACK_MARGIN = limit("pack_margin", 0.5, "", PHYSICAL,
                    "uv_pack keeps its margin around every island, so a margin of half the UV square leaves no room for "
                    "any island. Blender's unwrap and smart project take up to 1 (uv_margin).")
SMALLEST_FEATURE_MULTIPLIER = limit("smallest_feature_multiplier", 0.01, "", PHYSICAL,
                                    "At 0.01 every feature of a material preset grows a hundredfold, millimetre grain "
                                    "and pores to decimetres; the preset's own size fields set larger patterns.")
FEWEST_MASK_PATCHES = limit("fewest_mask_patches", 0.01, "1/m", PHYSICAL,
                            "One wear or dirt patch per 100 m already spans a whole building, the largest surface one "
                            "layer weathers.")
FEWEST_GROWTH_RINGS = limit("fewest_growth_rings", 1.0, "1/m", PHYSICAL,
                            "The widest growth rings, of fast-grown poplar or eucalyptus, are a few centimetres; below "
                            "one ring per metre a board shows no ring at all.")
FEWEST_STONE_CELLS = limit("fewest_stone_cells", 0.1, "1/m", PHYSICAL,
                           "A stone cell or colour patch more than 10 m across is a rock face, built as geometry "
                           "rather than drawn as a texture cell.", "fracture or heightfield")
FEWEST_THREADS = limit("fewest_threads", 1.0, "1/m", PHYSICAL,
                       "The coarsest weaves (sacking, rope mats) have some 100 threads per metre; below one per metre "
                       "there is no weave left.")
SMALLEST_CRUMB = limit("smallest_crumb", 0.002, "m", PHYSICAL,
                       "Soil crumbs and moss clumps are at least about 2 mm across; finer grains read as a flat colour.")
SMALLEST_PATTERN_SPACING = limit("smallest_pattern_spacing", 0.005, "m", PHYSICAL,
                                 "The finest bark fissures and turf tufts lie about 5 mm apart; ripples, fissures or "
                                 "tufts packed closer read as plain grain.")
SMALLEST_TEXTURE_REPEAT = limit("smallest_texture_repeat", 0.001, "", PHYSICAL,
                                "At a thousandth of a repeat the UV square shows 8 pixels of the largest image "
                                "(image_size); fewer repeats stretch single pixels over the whole surface.")
SMALLEST_SIZE_STEP = limit("smallest_size_step", 0.1, "", PHYSICAL,
                           "A size factor per branch order below 0.1 shrinks leaves tenfold at each order inward, so "
                           "they vanish one order in from the twigs.")
SHORTEST_SIDE_TWIG = limit("shortest_side_twig", 0.1, "", PHYSICAL,
                           "A side twig under a tenth of its cluster's twig is a stub with no room for its own leaves.")
SHORTEST_LEAF_SHAPE = limit("shortest_leaf_shape", 0.3, "", PHYSICAL,
                            "Leaves of one tree differ in length about threefold at most (shade against sun leaves); "
                            "0.3 of the card length is the shortest shape.")
FEWEST_LEAVES_PER_METRE = limit("fewest_leaves_per_metre", 0.1, "1/m", PHYSICAL,
                                "One leaf per 10 m of leafy branch already leaves the crown bare; a leafless tree "
                                "takes no tree_leaves call.")
FEWEST_RING_SEGMENTS_PER_METRE = limit("fewest_ring_segments_per_metre", 1.0, "1/m", PHYSICAL,
                                       "At one segment per metre of girth every branch thinner than ring_segments.min "
                                       "metres round already gets the fewest segments; fewer would leave even a 30 m "
                                       "giant trunk a coarse polygon.")
LEAST_BARK_GRAIN = limit("least_bark_grain", 1.0, "", PHYSICAL,
                         "Bark relief runs along the branch (fissures, ridges, plates) and at 1 it is round; bands "
                         "around the trunk, such as cherry lenticels, come from the bark material.")
SMALLEST_SPLIT_ANGLE = limit("smallest_split_angle", 1.0, "deg", PHYSICAL,
                             "Below one degree smart project cuts every curved surface with fewer than 360 segments "
                             "around into single-face islands.")
THINNEST_WIRE = limit("thinnest_wire", 0.25, "px", PHYSICAL,
                      "A wireframe line under a quarter pixel covers too little of any pixel to show after filtering.")
WIRE_WIDTH = limit("wire_width", 32.0, "px", PHYSICAL,
                   "Lines 32 px wide already hide the faces between edges in a full-size frame; the default is one "
                   "pixel.")
