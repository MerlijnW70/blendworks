"""Named limits of the shape, terrain, tree, scatter and liquid tools (commands a to l)."""
from .limit_base import BLENDER, MEMORY, PHYSICAL, PROTOCOL, TIME, limit
from .limits import MAX_MESH_FROM_DATA_FACES, MAX_MESH_VERTICES

PATH_LENGTH = limit("path_length", 1_024, "characters", PROTOCOL,
                    "A file path in a request, relative to the workspace; 1024 characters hold any folder depth a "
                    "project uses.")
ELEMENT_NAME_LENGTH = limit("element_name_length", 63, "bytes", BLENDER,
                            "Blender keeps bone, constraint, shape key and NLA track names to 63 bytes and cuts "
                            "longer ones, which would then no longer match.")
CHECKPOINT_NAME_LENGTH = limit("checkpoint_name_length", 64, "characters", PROTOCOL,
                               "A checkpoint name becomes its file name in the workspace; 64 characters keep the "
                               "path short on every file system.")
MAX_DRACO_LEVEL = limit("draco_level", 10, "", BLENDER, "The glTF exporter's Draco compression levels run from 0 to 10.")
LEAST_CONVEXITY = limit("least_convexity", 0.5, "", PHYSICAL,
                        "Volume over convex hull volume of stones and fragments lies above one half; a lower target "
                        "would be met before the first pass.")
MAX_METABALL_LEVEL = limit("metaball_level", 4.0, "", BLENDER,
                           "Each sphere's stiffness is the field level over 0.42, so that a lone sphere keeps its "
                           "radius; Blender caps stiffness at 10.")
LEAST_METABALL_LEVEL = limit("least_metaball_level", 0.05, "", BLENDER,
                             "Below 0.05 the stiffness (level over 0.42) nears Blender's floor of 0, where a sphere "
                             "adds no field.")
MAX_LOD_LEVELS = limit("lod_levels", 8, "levels", MEMORY,
                       "Each level of detail is a decimated copy of the mesh; game engines use up to 8 (Unreal "
                       "Engine's import limit).")
MAX_LOD_RATIO = limit("lod_ratio", 0.99, "", PHYSICAL,
                      "A level of detail keeps a share of the triangles of LOD0 and must drop at least 1 % of them, "
                      "or it is LOD0 again.")
ZERO_TOLERANCE = limit("zero_tolerance", 0.01, "m", PHYSICAL,
                       "A distance under which a height or an offset counts as zero; past 1 cm it would erase real "
                       "detail such as bevels, chamfers and engraving.")
LEAST_BIT_DEPTH = limit("least_bit_depth", 8, "bits", BLENDER, "Saved images hold 8 bits per channel or more.")
MAX_BIT_DEPTH = limit("bit_depth", 16, "bits", BLENDER, "PNG holds at most 16 bits per channel.")
LEAST_CAMERA_MILLIMETRES = limit("least_camera_millimetres", 1.0, "mm", BLENDER,
                                 "Blender's focal lengths and sensor sizes start at 1 mm.")
MAX_FOCAL_LENGTH = limit("focal_length", 5_000.0, "mm", PHYSICAL,
                         "The longest camera lenses made reach about 5 000 mm, the end of Blender's lens slider.")
MAX_SENSOR_SIZE = limit("sensor_size", 200.0, "mm", PHYSICAL,
                        "Film and sensors up to large format: 8x10 inch sheet film exposes about 200 by 250 mm.")
LEAST_F_NUMBER = limit("least_f_number", 0.5, "", PHYSICAL,
                       "f/0.5 is the widest aperture a lens in air can have; the fastest lenses made are about f/0.7.")
MAX_F_NUMBER = limit("f_number", 128.0, "", PHYSICAL,
                     "Large-format lenses stop down to about f/128, the smallest apertures made.")
MAX_APERTURE_BLADES = limit("aperture_blades", 16, "blades", BLENDER, "Blender draws bokeh with at most 16 blades.")
LEAST_APERTURE_RATIO = limit("least_aperture_ratio", 0.01, "", BLENDER,
                             "Blender's anamorphic aperture ratio starts at 0.01.")
MAX_APERTURE_RATIO = limit("aperture_ratio", 10.0, "", PHYSICAL,
                           "Anamorphic lenses squeeze bokeh by about 2; 10 leaves room for stylised looks and its "
                           "inverse 0.1 for the other axis.")
MAX_CAMERA_SHIFT = limit("camera_shift", 2.0, "frames", PHYSICAL,
                         "Lens shift in frame widths; at 2 the frame lies wholly beside the lens axis, far past any "
                         "shift lens, and Blender's slider ends there.")
MAX_EXPOSURE_STOPS = limit("exposure_stops", 32.0, "stops", BLENDER,
                           "Blender's scene exposure runs from -32 to 32 stops.")
LEAST_SHUTTER = limit("least_shutter", 1e-6, "s", PHYSICAL,
                      "A microsecond, past the 1/32 000 s of the fastest camera shutters.")
MAX_SHUTTER = limit("shutter", 60.0, "s", PHYSICAL,
                    "Cameras time exposures up to 30 s; a minute covers timed night exposures.")
LEAST_ISO = limit("least_iso", 1.0, "", PHYSICAL,
                  "The ISO arithmetic speed scale starts at 1; the slowest films and sensors are near ISO 6 to 50.")
MAX_ISO = limit("iso", 409_600.0, "", PHYSICAL, "ISO 409 600 is the top setting of current professional cameras.")
LEAST_EXPOSURE_VALUE = limit("least_exposure_value", -10.0, "EV", PHYSICAL,
                             "EV100 of a moonless, overcast night landscape, the darkest scene a camera records.")
MAX_EXPOSURE_VALUE = limit("exposure_value", 30.0, "EV", PHYSICAL,
                           "EV100 far past any lit surface: sunlit snow is about EV 16, and only the sun's own disc "
                           "is brighter than EV 30.")
LEAST_DISPLAY_GAMMA = limit("least_display_gamma", 0.01, "", PHYSICAL,
                            "Display gamma divides the exponent, so 0 has no meaning; at 0.01 every mid-grey already "
                            "maps to black (0.5 to the power 100).")
MAX_DISPLAY_GAMMA = limit("display_gamma", 5.0, "", BLENDER, "Blender's display gamma runs up to 5.")
MAX_LIGHT_POWER = limit("light_power", 1_000_000.0, "W", PHYSICAL,
                        "A million watts of light, past any searchlight or stadium mast, where Blender's power slider "
                        "ends.")
LEAST_SPOT_ANGLE = limit("least_spot_angle", 1.0, "deg", BLENDER, "Blender's spot cones open at least 1 degree.")
MAX_WORLD_STRENGTH = limit("world_strength", 1000.0, "", PHYSICAL,
                           "A world or sky strength multiplies the environment's light; 1000 lifts the dimmest HDRI or "
                           "a night sky far past full daylight.")
MAX_FRAME = limit("frame", 1_048_574, "frames", BLENDER, "Blender's frame range ends at 1 048 574 (MAXFRAME).")
LEAST_CYCLE_FRAMES = limit("least_cycle_frames", 8, "frames", PHYSICAL,
                           "A gait or prop cycle needs about 8 frames to show its contact, passing and lift poses.")
MAX_CYCLE_FRAMES = limit("cycle_frames", 2_400, "frames", TIME,
                         "A preset keys every moving bone on every frame of its cycle; 2 400 frames is 100 s at 24 "
                         "frames a second.")
MAX_CLIP_KEYS = limit("clip_keys", 4_096, "keys", PROTOCOL, "Keys sent inline in one call.")
MAX_KEY_VALUE = limit("key_value", 1_000_000.0, "", PHYSICAL,
                      "A key holds a location in metres, a rotation in degrees, a scale or a shape key value; a "
                      "million is past the edge of the world (coordinate) and past 2 700 turns.")
MAX_RIG_ROLES = limit("rig_roles", 128, "roles", PROTOCOL,
                      "Roles of one rig sent inline; a humanoid with every finger has about 60.")
MAX_SPEED = limit("speed", 100.0, "m/s", PHYSICAL,
                  "Speeds of things moving through a scene: the fastest land animals run 30 m/s and race cars reach "
                  "about 100 m/s.")
LEAST_CADENCE = limit("least_cadence", 10.0, "steps/min", PHYSICAL, "One step in six seconds, slower than any walk.")
MAX_CADENCE = limit("cadence", 600.0, "steps/min", PHYSICAL,
                    "Ten steps a second, the stride rate of small running animals.")
MAX_CLIP_ROTATION = limit("clip_rotation", 720.0, "deg", PHYSICAL,
                          "Open and turn presets rotate a part up to two full turns in one clip; for more use spin.")
MAX_SPIN_TURNS = limit("spin_turns", 100.0, "turns", PHYSICAL,
                       "Turns in one clip; at 100 turns in a 2 s clip a part spins 50 times a second, past what frames "
                       "can show.")
MAX_IK_CHAIN_BONES = limit("ik_chain_bones", 16, "bones", PHYSICAL,
                           "Limbs chain 2 or 3 bones; 16 covers spines, tails and tentacles.")
MAX_ANISOTROPY = limit("anisotropy", 0.95, "", PHYSICAL,
                       "Henyey-Greenstein g: at 1 light scatters only straight on; haze and cloud droplets reach about "
                       "0.9.")
LEAST_BAKE_SIZE = limit("least_bake_size", 16, "px", PHYSICAL,
                        "A baked map smaller than 16 px holds less than the default 16 px margin around one island.")
MAX_BAKE_CHANNELS = limit("bake_channels", 6, "channels", PROTOCOL,
                          "The bakeable channels: base_color, roughness, metallic, emission, normal and ao.")
MAX_ATLAS_RULES = limit("atlas_rules", 64, "rules", PROTOCOL, "Image size rules of one bake sent inline as JSON.")
LEAST_BAKE_SECONDS = limit("least_bake_seconds", 1.0, "s", TIME,
                           "Setting up a bake alone takes about a second; a shorter time limit always fails.")
MAX_CLOUD_LAYERS = limit("cloud_layers", 6, "layers", TIME,
                         "Each layer adds its noise to the world shader and may add a volume the renderer marches; six "
                         "hold one layer per height band with room to spare.")
LEAST_EXTINCTION_SCALE = limit("least_extinction_scale", 0.01, "", PHYSICAL,
                               "A hundredth of a genus's extinction leaves a faint veil; less draws nothing.")
MAX_EXTINCTION_SCALE = limit("extinction_scale", 20.0, "", PHYSICAL,
                             "Twenty times a genus's extinction is past the densest storm cores.")
MAX_BRIGHTNESS_SCALE = limit("brightness_scale", 10.0, "", PHYSICAL,
                             "Multiplies a modelled radiance; ten times is past any real surface or cloud in sunlight.")
MAX_VOLUME_BOUNCES = limit("volume_bounces", 128, "bounces", TIME,
                           "Each bounce traces one more scattering event per path; past 128 clouds grow no brighter and "
                           "renders only take longer.")
MAX_HELIX_TURNS = limit("helix_turns", 1_000.0, "turns", PHYSICAL,
                        "Coil springs and screw threads have up to a few hundred turns; the segment count is checked "
                        "against path_points as well.")
LEAST_LETTER_SPACING = limit("least_letter_spacing", 0.1, "", PHYSICAL,
                             "At a tenth of the font's spacing letters already overlap into one blot.")
MAX_LETTER_SPACING = limit("letter_spacing", 10.0, "", BLENDER, "Blender's character spacing runs up to 10.")
MAX_REPEATS = limit("repeats", 720, "copies", TIME,
                    "Each copy is laid out and cut on its own; 720 is a mark every half degree around a dial.")
MAX_LABEL_NUMBER = limit("label_number", 1e9, "", PROTOCOL,
                         "Numbers printed by a repeat; past a billion they are no longer read as dial or scale labels.")
MAX_EROSION_TILES = limit("erosion_tiles", 64, "tiles", MEMORY,
                          "Tiles eroded together are held as one float64 grid with copies for the change and the mask; "
                          "64 tiles of the largest resolution take about 1 GB per copy.")
MAX_THERMAL_SWEEPS = limit("thermal_sweeps", 20_000, "sweeps", TIME, "Each thermal sweep visits every cell of the grid.")
LEAST_TALUS_ANGLE = limit("least_talus_angle", 1.0, "deg", PHYSICAL,
                          "Below a degree every slope slides and the ground flows flat; real talus stands at 30 to 45 "
                          "degrees.")
MAX_TALUS_ANGLE = limit("talus_angle", 89.0, "deg", PHYSICAL,
                        "The tangent of the talus angle sets the stable height step; at 90 degrees it is infinite.")
MAX_DROPLETS = limit("droplets", 2_000_000, "droplets", TIME, "Each droplet runs up to its lifetime in steps.")
MAX_DROPLET_INERTIA = limit("droplet_inertia", 0.99, "", PHYSICAL, "At 1 a droplet would never turn downhill.")
MAX_SEDIMENT_CAPACITY = limit("sediment_capacity", 1_000.0, "", PHYSICAL,
                              "The capacity factor Kc of droplet erosion is about 1 to 30 in practice; 1000 already "
                              "strips a slope in one pass.")
MAX_DROPLET_GRAVITY = limit("droplet_gravity", 1_000.0, "", PHYSICAL,
                            "How fast a droplet speeds up per metre it descends; 4 to 10 is usual, and 1000 already "
                            "makes every droplet race.")
MAX_EROSION_BRUSH = limit("erosion_brush", 1_000.0, "m", MEMORY,
                          "The brush lists every grid cell within its radius for each droplet of a batch, (radius / "
                          "grid spacing) squared cells. 1000 m was the cap before and stays: the schema cannot see the "
                          "grid spacing, so a spacing-aware check belongs in erode itself (known gap, owned by the "
                          "landforms job).")
MAX_DROPLET_LIFETIME = limit("droplet_lifetime", 10_000, "steps", TIME, "Steps one droplet may run.")
MAX_UV_COORDINATE = limit("uv_coordinate", 1_000.0, "", PHYSICAL,
                          "UVs a thousand tiles out still place a texel of an 8192 px texture within half a texel in "
                          "float32.")
MAX_FACE_CORNERS = limit("face_corners", 10_000, "corners", TIME,
                         "Corners of one n-gon; Blender triangulates n-gons for drawing and export, slower the larger.")
MAX_MATERIAL_SLOTS = limit("material_slots", 32_767, "slots", BLENDER, "Blender's material slot indices end at 32 767.")
MAX_BEVEL_RESOLUTION = limit("bevel_resolution", 32, "segments", BLENDER,
                             "Blender's curve bevel resolution ends at 32 segments a quarter.")
MAX_CURVE_RESOLUTION = limit("curve_resolution", 64, "segments", MEMORY,
                             "Segments between two points of a smooth curve; with 10 000 points (curve_points) a curve "
                             "evaluates to 640 000 segments.")
MAX_TEXT_SIZE = limit("text_size", 10_000.0, "m", BLENDER, "Blender's text size ends at 10 000.")
MAX_GRID_SIDE = limit("grid_side", int(MAX_MESH_VERTICES.plain() ** 0.5), "vertices", MEMORY,
                      "Vertices per side of a square grid: the square root of mesh_vertices.")
MAX_TILE_INDEX = limit("tile_index", 1_000, "tiles", PHYSICAL,
                       "A thousand tiles each way of 100 m tiles reach 100 km, half the coordinate range.")
BASE_NAME_LENGTH = limit("base_name_length", 60, "characters", PROTOCOL,
                         "A name the call extends with suffixes or population names; 60 characters leave room for "
                         "them within Blender's 255-byte names.")
MAX_WIND_SPEED = limit("wind_speed", 40.0, "m/s", PHYSICAL,
                       "Wind at 10 m height; the wave spectra used (JONSWAP, Pierson-Moskowitz) are fitted to winds "
                       "up to a severe storm of about 40 m/s.")
MAX_FETCH = limit("fetch", 10_000_000.0, "m", PHYSICAL,
                  "Open water upwind; 10 000 km spans the widest ocean, far past where a wind sea stops growing.")
LEAST_WAVE_CELLS = limit("least_wave_cells", 16, "cells", PHYSICAL,
                         "With fewer than 16 cells a side a wave mesh cannot show crests and troughs.")
MAX_WAVE_CELLS = limit("wave_cells", 512, "cells", TIME,
                       "The wave field is summed from the spectrum at every vertex; 512 cells a side is 263 000 "
                       "vertices.")
LEAST_MANNING_N = limit("least_manning_n", 0.01, "s/m^(1/3)", PHYSICAL,
                        "Manning's n of the smoothest channels (glass, finished concrete) is about 0.01.")
MAX_MANNING_N = limit("manning_n", 0.2, "s/m^(1/3)", PHYSICAL,
                      "Manning's n of dense brush and timber floodplains reaches about 0.2.")
MAX_LIQUID_TILT = limit("liquid_tilt", 60.0, "deg", PHYSICAL,
                        "A sloshing or accelerated liquid surface tilts by atan(a / g); 60 degrees is 1.7 g, past any "
                        "carried or driven container.")
MAX_SPILL_AREA = limit("spill_area", 1_000.0, "m^2", PHYSICAL,
                       "A spill from a cup covers a fraction of a square metre; 1000 square metres is a burst tank.")
LEAST_CONTACT_ANGLE = limit("least_contact_angle", 1.0, "deg", PHYSICAL,
                            "Contact angles lie between complete wetting (0) and none (180); the film thickness needs "
                            "both ends open.")
MAX_CONTACT_ANGLE = limit("contact_angle", 179.0, "deg", PHYSICAL,
                          "Contact angles lie between complete wetting (0) and none (180); the film thickness needs "
                          "both ends open.")
MAX_DRIPS = limit("drips", 64, "drips", TIME, "Each drip is traced down the outside wall on its own.")
MAX_LIQUID_VOLUME = limit("liquid_volume", 1_000_000.0, "l", PHYSICAL,
                          "A thousand cubic metres, a large storage tank; the container's own capacity is checked too.")
MAX_WALL_GAP = limit("wall_gap", 0.01, "m", PHYSICAL,
                     "The gap between a liquid and its glass only separates the two surfaces for refraction; wider "
                     "than 1 cm it shows as an air layer.")
LEAST_CAVITY_VOXELS = limit("least_cavity_voxels", 16, "voxels", PHYSICAL,
                            "Fewer than 16 voxels across cannot tell a container's wall from its cavity.")
MAX_CAVITY_VOXELS = limit("cavity_voxels", 160, "voxels", MEMORY,
                          "The cavity is found on a cube of voxels; 160 a side is 4.1 million cells.")
MAX_STONE_GROUP_DENSITY = limit("stone_group_density", 10.0, "1/m^2", PHYSICAL,
                                "Groups of shore stones come at most ten to the square metre, past which their stones "
                                "overlap into one bed.")
MAX_STONES_PER_GROUP = limit("stones_per_group", 1_000.0, "stones", TIME,
                             "A mean of a thousand stones in a group is a talus slope; each stone is placed and thinned "
                             "against its neighbours.")
LEAST_STONE_SIZE = limit("least_stone_size", 0.005, "m", PHYSICAL,
                         "Gravel from 5 mm up; finer sediment is sand, which is a texture, not a stone.")
MAX_STONE_SIZE = limit("stone_size", 100.0, "m", PHYSICAL,
                       "The longest side of the largest boulders of a shore (rock fall blocks, glacial erratics) is "
                       "tens of metres.")
MAX_STONE_CLASSES = limit("stone_classes", 8, "classes", TIME,
                          "One set of stone meshes is built for each class (fracture, chip, abrade); eight steps from "
                          "angular to round are finer than the eye tells apart.")
MAX_STONE_VARIANTS = limit("stone_variants", 8, "meshes", TIME,
                           "Meshes built for each class; eight give a shore no two alike next to each other.")
MAX_BUBBLES = limit("bubbles", 5_000, "bubbles", MEMORY, "Each bubble is a small closed mesh in the bubbles object.")
MAX_GRAMMAR_TEXT = limit("grammar_text", 1_024, "characters", PROTOCOL, "One axiom or production sent as text.")
MAX_GRAMMAR_RULES = limit("grammar_rules", 64, "rules", TIME,
                          "Every module of every derivation step is matched against the rules.")
MAX_GRAMMAR_CONSTANTS = limit("grammar_constants", 64, "constants", PROTOCOL, "Named numbers of one grammar sent inline.")
MAX_GRAMMAR_NAME = limit("grammar_name_length", 32, "characters", PROTOCOL,
                         "Names of grammar constants, written out in every condition and successor that uses them.")
MAX_GRAMMAR_NUMBER = limit("grammar_number", 1e9, "", PHYSICAL,
                           "Numbers in a grammar are lengths, angles, widths and counts; a billion is past them all.")
MAX_DERIVATION_STEPS = limit("derivation_steps", 100, "steps", TIME,
                             "Steps of a derivation; growth is capped by lsystem_modules, so 100 serves grammars that "
                             "grow slowly.")
LEAST_WIDTH_RATIO = limit("least_width_ratio", 0.05, "", PHYSICAL,
                          "A branch thinner than a twentieth of its parent is lost beside it.")
MAX_TROPISM_BEND = limit("tropism_bend", 100.0, "", PHYSICAL,
                         "The turtle turns by e |H x T| radians after each step; at 100 it already turns fully towards "
                         "T in one step, so a larger e or T changes nothing.")
MAX_ORGAN_SYMBOLS = limit("organ_symbols", 8, "symbols", PROTOCOL,
                          "Organ symbols of one plant, each placed as its own group of copies.")
SYMBOL_LENGTH = limit("symbol_length", 1, "characters", PROTOCOL, "A module symbol is one letter.")
MAX_MESH_FROM_DATA_CORNERS = limit("mesh_from_data_corners", 4 * MAX_MESH_FROM_DATA_FACES.plain(), "corners", PROTOCOL,
                                   "Face corners sent inline as JSON: four for each of mesh_from_data_faces.",
                                   "import (a mesh file in the workspace)")
MAX_CLUMP_BLADES = limit("clump_blades", 400, "blades", TIME,
                         "Blades of one clump are shaped one by one; the triangle budget caps their detail as well.")
LEAST_PETALS = limit("least_petals", 3, "petals", PHYSICAL, "Flowers have at least three petals.")
MAX_PETALS = limit("petals", 40, "petals", PHYSICAL, "Daisies and asters carry up to about 40 ray florets.")
MAX_BASE_LEAVES = limit("base_leaves", 8, "leaves", PHYSICAL, "Leaves at the base of a wildflower's stem.")
MAX_SIDE_SHOOTS = limit("side_shoots", 6, "shoots", PHYSICAL, "Side shoots of a fallen twig.")
MAX_PEBBLE_FLATNESS = limit("pebble_flatness", 0.9, "", PHYSICAL,
                            "At 1 a pebble would be a disc with no thickness; 0.9 is a flat skimming stone.")
MAX_PEBBLE_ELONGATION = limit("pebble_elongation", 2.0, "", PHYSICAL,
                              "Pebbles up to three times as long as wide, as long river pebbles.")
MAX_ELEMENT_TRIANGLES = limit("element_triangles", 20_000, "triangles", TIME,
                              "Triangle budget of one ground-cover element; the renderer draws it once per instance, "
                              "millions of times.")
MAX_ELEMENT_VARIANTS = limit("element_variants", 16, "variants", TIME,
                             "Each variant is its own element mesh, built and planned on its own.")
MAX_COVER_DENSITY = limit("cover_density", 100_000.0, "1/m^2", PHYSICAL,
                          "Elements per square metre: 100 000 is one every 3 mm, past the densest moss or lawn; the "
                          "instance budget caps the count as well.")
LEAST_CLUMP_SIZE = limit("least_clump_size", 1.0, "elements", PHYSICAL, "A clump holds at least one element.")
MAX_CLUMP_SIZE = limit("clump_size", 1_000.0, "elements", PHYSICAL,
                       "A thousand elements is a dense tussock or patch; larger groups are populations of their own.")
MAX_ATTRIBUTE_VALUE = limit("attribute_value", 1_000_000.0, "", PHYSICAL,
                            "Terrain attributes (heights and depths in metres, slopes in degrees, curvature per metre) "
                            "stay well inside a million.")
MAX_DISTANCE_MASKS = limit("distance_masks", 8, "masks", TIME,
                           "Each distance mask measures every candidate point against its objects' surfaces.")
LEAST_WIDENING = limit("least_widening", 1.0, "", PHYSICAL,
                       "A widening factor of 1 leaves an element as it is; below 1 it would narrow it.")
MAX_WIDENING = limit("widening", 4.0, "", PHYSICAL, "Widened past fourfold, a far blade reads as a smear.")
MAX_POPULATIONS = limit("populations", 16, "populations", TIME,
                        "Each population builds its elements and plans its instances over the whole surface.")
MAX_DENSITY_SCALE = limit("density_scale", 100.0, "", PHYSICAL,
                          "Multiplies every population's density; the instance budget caps the count as well.")
MAX_VIEW_CAMERAS = limit("view_cameras", 8, "cameras", TIME,
                         "Every candidate point is tested against the view of each camera.")
MAX_VIEW_MARGIN = limit("view_margin", 2.0, "", PHYSICAL,
                        "A margin of twice the frame on every side covers what a panning camera swings past.")
MAX_CONTACT_DARKENING = limit("contact_darkening", 0.36, "", PHYSICAL,
                              "The darkest soil of the CC0 forest-ground photo is 0.64 of its median; darkening past "
                              "0.36 would go below it.")
MAX_LEAF_ASPECT = limit("leaf_aspect", 1.5, "", PHYSICAL,
                        "Kidney-shaped leaves such as ginkgo grow up to about 1.5 times wider than long.")
MAX_ARMATURE_BONES = limit("armature_bones", 512, "bones", TIME,
                           "Bones of one armature; skinning weighs every vertex against every deforming bone, and a "
                           "detailed character rig with fingers and face has a few hundred.")
LEAST_CARD_BLADES = limit("least_card_blades", 2, "blades", PHYSICAL,
                          "A card stands for a group of blades; a single blade is drawn as geometry.")
MAX_CARD_BLADES = limit("card_blades", 64, "blades", PHYSICAL,
                        "Past 64 blades across one card a blade is only a few texels wide on a 1024 px card.")
LEAST_SCRATCH_DENSITY = limit("least_scratch_density", 0.1, "", PHYSICAL,
                              "A tenth of the default scratch density leaves a few scattered scratches.")
MAX_SCRATCH_DENSITY = limit("scratch_density", 20.0, "", PHYSICAL,
                            "Twenty times the default scratch density already covers a surface as a brushed finish.")
SHORTEST_RAY_REACH = limit("shortest_ray_reach", 0.001, "m", PHYSICAL,
                           "Occlusion rays shorter than 1 mm darken only creases under a millimetre wide, which no "
                           "render of a hand-sized part or larger shows.")
SHORTEST_DROPLET_STEP = limit("shortest_droplet_step", 0.001, "m", PHYSICAL,
                              "At 1 mm a step a droplet travels at most 10 m in its longest life (droplet_lifetime), "
                              "and each step erodes only a step-sized patch; shorter steps carve nothing.")
SMALLEST_EROSION_BRUSH = limit("smallest_erosion_brush", 0.01, "m", PHYSICAL,
                               "Droplets model gullies that running water carves, a centimetre wide and more; finer "
                               "rills are texture. erode widens any brush to 1.5 grid spacings as well.")
SMALLEST_BLADE_WIDTH = limit("smallest_blade_width", 0.0002, "m", PHYSICAL,
                             "The finest grass blades, such as fine fescues, are about 0.2 mm wide at the root.")
SMALLEST_PLANT_PART = limit("smallest_plant_part", 0.0005, "m", PHYSICAL,
                            "Petals, flower discs, stems, base leaves and twigs of ground plants are at least about "
                            "half a millimetre across.")
SMALLEST_ELEMENT_SIZE = limit("smallest_element_size", 0.001, "m", PHYSICAL,
                              "A blade or a petal shorter than 1 mm is moss-sized texture, not geometry, and a pebble "
                              "under 2 mm across is sand on the Wentworth scale.")
SHORTEST_LEAF = limit("shortest_leaf", 0.002, "m", PHYSICAL,
                      "The smallest leaves and twigs of forest-floor litter, such as conifer scale leaves, are about "
                      "2 mm long.")
SMALLEST_COVER_PATCH = limit("smallest_cover_patch", 0.01, "m", PHYSICAL,
                             "At the densest cover (cover_density, one element every 3 mm) a 1 cm clump or band holds "
                             "about 30 elements; a narrower one holds too few to read as a clump or a band.")
SMALLEST_INSTANCE_SCALE = limit("smallest_instance_scale", 0.01, "", PHYSICAL,
                                "Elements are built at their real size; a hundredth turns a 10 cm plant into 1 mm, "
                                "the smallest_element_size.")
SMALLEST_ARC = limit("smallest_arc", 1.0, "deg", PHYSICAL,
                     "An arc or a spherical cap under one degree bends from a straight row or a flat disc by less "
                     "than 0.5 % of its width.", "waypoints (a straight row) or phyllotaxis disc mode")
SMALLEST_ORGAN_SCALE = limit("smallest_organ_scale", 0.001, "", PHYSICAL,
                             "A thousandth turns a 1 m organ template into 1 mm, smaller than any bud or stamen a "
                             "plant model shows.")
