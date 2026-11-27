# Limits

Every bound in a tool schema comes from one named limit of `bridge/blendworks_bridge/limits.py` (the tool families'
limits are defined in `limits_parts.py` and `limits_parts_more.py` and read through it). This table lists
them all, each with the kind of reason and the reason for its value. One quantity has one limit in every tool: a
length is a length in `sweep` and in `atmosphere`. `npm run check` fails when a schema bound has no named limit,
when a bound differs from its limit, or when a limit is missing here (`bridge/tests/test_world_scale.py`); this file
is written by `bridge/tests/limits_doc.py`.

Kinds of reason: **physical** (the range of the quantity in the world), **memory** (what one call may allocate),
**time** (how long one call may run), **blender** (a limit of Blender itself), **protocol** (the request format).

Bounds that define what a field holds are not limits and are not listed: a minimum of 0 (the sign of a quantity),
an integer minimum of 1 (at least one), a non-empty string, a list that may be empty or needs one item, and the
number of items of a tuple of at most four (a vector, a pair, a colour).

## How big a scene can be

- Positions reach 200 km from the origin (`coordinate`), lengths and distances 400 km (`length`), heights and
  displacements 20 km (`relief`). Clip distances, visibility, tile sizes, cloud fields, haze domains, scatter and
  ground-cover regions, liquid bodies and render bounds all use these.
- Counts that cost memory derive from `scene_memory`: half of what the bridge process may use, read when it starts
  from its container's cgroup limit (`memory.max`, or `memory.limit_in_bytes`) or else the physical memory. In the
  judge's 8 GB container that is 4 GB, so `ground_cover` allows 6.7 million instances there and its default of one
  million (640 MB) fits. The two rows below that depend on it show the value on the machine that wrote this file.
- Ask before you build: `validate` checks a whole plan of calls against these limits and the names earlier calls
  make, and lists every problem at once without running anything.

## Precision far from the origin

Blender stores positions as float32: a position p is held to within |p| * 2^-24, 0.5 mm at 16 km and 7.8 mm anywhere
up to 262 km. Two things keep that from showing:
- An object's vertices are stored relative to the object, so a rock, tree or tile keeps its full detail wherever it
  stands; only its placement carries the error above (`test_world_scale.py` places objects 150 km out within 7.9 mm).
- The renderers flatten every mesh into world space in float32, which would round geometry next to a camera at 150 km
  to 15.6 mm. So every render the bridge starts is camera-relative (`floating_origin.py`): when the camera that
  render uses stands farther than `safe_camera_distance` (16 384 m) from the origin horizontally, the world moves by
  the camera's x and y, rounded to whole metres, for that render and every changed value is put back exactly
  afterwards. Every root object, and every root of a collection an object instances, is parented to one temporary
  empty at minus the offset, so animation, drivers, parents and constraints in local or relative spaces evaluate as
  before; Limit Location in world space and Child Of (x and y location on) get offset numbers; instanced collections
  get an offset instance offset; shaders that read the world position (Geometry Position, Vector Transform of a point
  to or from world space) get the offset added back, so clouds, cloud shadows, rain and world-placed textures fall
  where they fall unmoved. Before rendering, every object's evaluated world matrix, every bone's pose and every
  evaluated mesh's bounds are measured against the unmoved scene; settings no moved frame can follow (emitter
  particles, modifiers whose texture reads global coordinates, drivers that read world positions, a constraint such as
  Copy Location with offset in world space) or a failed measurement keep the world in place: that render runs unmoved,
  at plain float32 precision, and the reply names the reason under `camera_relative`. A render without its own camera
  (preview turntables, close-ups) moves only when the camera it uses stands far out. Heights stay, so haze height
  falloff keeps its meaning; a position pass is camera-relative. Not covered: with motion blur the measurement is
  taken at the frame itself, not at every subframe; an instanced collection whose instance offset is not a multiple
  of the float32 step at the moved distance keeps unmoved precision for its instances; drivers on anything but
  transforms that read world positions through other paths are not seen. `test_floating_origin.py` renders a static,
  a keyframed, a Child Of, a driven, a collection-instanced and a world-Limit-Location cube 150 km out moved and
  unmoved, cloud sheets and volumes with their shadows, previews without a camera, and checks exact restore after a
  render and after a failure.
- `heightfield` refuses a tile whose `tile` times `size` would put an edge past the coordinate limit.

## Counts checked before the work

Tools whose work grows with a length, a scale or a count check the count first and refuse before allocating:
`roller_chain` (links from the path length over the pitch), `engrave` and `engrave_scale`, `tree_leaves`, the tree
foliage, `extrude`, `gear`, `sprocket`, `bevel` and the `bevel` and `screw` cases of `add_modifier`. `tree_mesh`
keeps the checks it had: with `lod` the ring density is chosen to meet the budget, the voxel junction estimates its
triangles from the tube area before remeshing, and a skin-joined bark mesh without `lod` has no vertex cap. The estimate of `add_modifier` does not cover a bevel limited by weight or vertex group, nor a
shrinkwrap over a subdivision; those are still refused once the modifier has been evaluated (or applied), against
`mesh_vertices`, and the call is undone.

## Known gaps outside this job

These keep a 10 km figure in code this job may not change; they are left to the jobs that own those files:
- `weather_build.py` (`HAZE_REACH`, 10 km): `weather` only adds haze when the visibility is under 10 km and caps its
  haze there. For landscape haze call `atmosphere` with the visibility you need, as `docs/examples/world_scale.py` does.
- `commands/lights.py`: `add_camera` sets a far clip of 10 km. Set `clip_end` with `camera_setup` (up to `length`).
- `erode`: the brush lists (radius / grid spacing)^2 cells per droplet; the schema cannot see the spacing, so the
  radius keeps its 1 km cap (`erosion_brush`) until `erode` checks the cell count itself.

## Table

| Limit | Value | Unit | Kind | Reason | Instead | Used by |
|---|---|---|---|---|---|---|
| `abrasion_passes` | 500 | passes | time | Each pass smooths every vertex once and measures the volume. | - | `abrade.iterations` |
| `anisotropy` | 0.95 | - | physical | Henyey-Greenstein g: at 1 light scatters only straight on; haze and cloud droplets reach about 0.9. | - | `atmosphere.anisotropy`, `valley_mist.anisotropy` |
| `aperture_blades` | 16 | blades | blender | Blender draws bokeh with at most 16 blades. | - | `camera_setup.aperture_blades` |
| `aperture_ratio` | 10 | - | physical | Anamorphic lenses squeeze bokeh by about 2; 10 leaves room for stylised looks and its inverse 0.1 for the other axis. | - | `camera_setup.aperture_ratio` |
| `armature_bones` | 512 | bones | time | Bones of one armature; skinning weighs every vertex against every deforming bone, and a detailed character rig with fingers and face has a few hundred. | - | `armature_create.bones`, `bone_add.bones`, `bone_edit.bones` |
| `aspect_ratio` | 20 | - | physical | An ellipse more than 20 times longer than wide reads as a slit. | - | `shell.aspect`, `tree_leaves.card.width`, `tree_mesh.bark_noise.grain` |
| `atlas_rules` | 64 | rules | protocol | Image size rules of one bake sent inline as JSON. | - | `bake.atlas_sizes` |
| `atmosphere_density` | 10 | - | physical | 1 is the standard atmosphere; ten times its air, dust or ozone already turns the sky grey, and thicker haze is weather's job. | - | `sky.air`, `sky.dust`, `sky.ozone`, `weather.dust` |
| `attenuation` | 1e+06 | 1/m | physical | A coefficient of a million per metre stops light within a micrometre: opaque at any size. | - | `material_liquid.absorption[]`, `material_liquid.scattering[]` |
| `attribute_value` | 1e+06 | - | physical | Terrain attributes (heights and depths in metres, slopes in degrees, curvature per metre) stay well inside a million. | - | `ground_cover.populations[].attribute.range[]`, `scatter.attribute_range[]` |
| `bake_channels` | 6 | channels | protocol | The bakeable channels: base_color, roughness, metallic, emission, normal and ao. | - | (internal) |
| `bake_margin` | 64 | px | physical | Island margins wider than 64 px only waste the atlas. | - | `bake.margin` |
| `bake_samples` | 1,024 | samples | time | Beyond 1024 samples a bake no longer gets cleaner. | - | `bake.samples.base_color`, `bake.samples.roughness`, `bake.samples.metallic`, `bake.samples.emission`, `bake.samples.normal`, `bake.samples.ao` |
| `bake_seconds` | 600 | s | time | The longest call the MCP server waits for. | - | `bake.time_limit` |
| `bake_size` | 4,096 | px | memory | Six float channels of 4096 px squared stay near the pixel guard. | - | `bake.size`, `bake.atlas_sizes[].size` |
| `base_leaves` | 8 | leaves | physical | Leaves at the base of a wildflower's stem. | - | `ground_cover.populations[].params.leaves`, `ground_element.params.leaves` |
| `base_name_length` | 60 | characters | protocol | A name the call extends with suffixes or population names; 60 characters leave room for them within Blender's 255-byte names. | - | `ground_cover.name`, `ground_cover.populations[].name`, `liquid_body.name`, `liquid_fill.name`, `shore_stones.name` |
| `bend_rate` | 20 | rad/m | physical | A bend of 20 radians per metre turns a twig tip a full circle within 30 cm; faster bends no longer read as growth. | - | `grow_tree.gravitropism.strength`, `grow_tree.phototropism.strength`, `grow_tree.wind.vector[]`, `grow_tree.sway.strength` |
| `bevel_resolution` | 32 | segments | blender | Blender's curve bevel resolution ends at 32 segments a quarter. | - | `curve_from_points.bevel_resolution` |
| `bevel_segments` | 100 | segments | memory | Each segment adds a row of faces along every bevelled edge, so bevel checks the result against mesh_vertices first; 100 segments make a round no render tells from a true arc. | - | `add_modifier.bevel.segments`, `bevel.segments`, `extrude_outline.bevel_segments`, `gear.bevel_segments`, `sprocket.bevel_segments` |
| `bit_depth` | 16 | bits | blender | PNG holds at most 16 bits per channel. | - | `image_save.depth`, `render_final.depth` |
| `blob_spheres` | 256 | spheres | time | Every cell of the metaball field sums the spheres that reach it. | - | `blob.points` |
| `bone_influences` | 8 | bones | protocol | glTF and game engines skin a vertex with at most 8 bones (two sets of four). | - | `skin_bind.max_influences` |
| `branch_orders` | 8 | orders | physical | Trees branch about six orders deep from trunk to twig; 8 covers every species. | - | `grow_tree.gravitropism.by_order`, `grow_tree.phototropism.by_order`, `grow_tree.gnarl.by_order`, `grow_tree.sway.by_order`, `grow_tree.hem.order`, `tree_leaves.orders` |
| `brightness_scale` | 10 | - | physical | Multiplies a modelled radiance; ten times is past any real surface or cloud in sunlight. | - | `clouds.layers[].brightness` |
| `bubbles` | 5,000 | bubbles | memory | Each bubble is a small closed mesh in the bubbles object. | - | `liquid_fill.bubbles` |
| `bump_depth` | 50 | mm | physical | Bump mapping fakes relief only a few centimetres deep before the shading breaks up; deeper relief is real geometry. | noise_displace (displaces the mesh in metres) | `material_layer.wood.bump`, `material_layer.worn_metal.bump`, `material_layer.brass.bump`, `material_layer.rust.bump`, `material_layer.stone.bump`, `material_layer.marble.bump` and 28 more |
| `cadence` | 600 | steps/min | physical | Ten steps a second, the stride rate of small running animals. | - | `animation_preset.cadence` |
| `camera_shift` | 2 | frames | physical | Lens shift in frame widths; at 2 the frame lies wholly beside the lens axis, far past any shift lens, and Blender's slider ends there. | - | `camera_setup.shift_x`, `camera_setup.shift_y` |
| `card_blades` | 64 | blades | physical | Past 64 blades across one card a blade is only a few texels wide on a 1024 px card. | - | `material_layer.grass_blade.card_blades`, `material_procedural.grass_blade.card_blades` |
| `cavity_voxels` | 160 | voxels | memory | The cavity is found on a cube of voxels; 160 a side is 4.1 million cells. | - | `liquid_fill.voxels` |
| `chain_links` | 2,000 | links | time | Each link adds its plates, rollers and pins to the chain mesh one by one. | - | (internal) |
| `chain_wheels` | 16 | wheels | protocol | Wheels of one chain drive listed inline; real drives have two to a handful. | - | `roller_chain.wheels` |
| `checkpoint_name_length` | 64 | characters | protocol | A checkpoint name becomes its file name in the workspace; 64 characters keep the path short on every file system. | - | `checkpoint.name`, `restore_checkpoint.name` |
| `checkpoints` | 64 | checkpoints | memory | Saved checkpoints kept on disk per session. | - | (internal) |
| `chips` | 500 | chips | time | Each chip is an exact plane cut of the whole solid. | - | `chip.count` |
| `clip_keys` | 4,096 | keys | protocol | Keys sent inline in one call. | - | `clip_keys.keys` |
| `clip_rotation` | 720 | deg | physical | Open and turn presets rotate a part up to two full turns in one clip; for more use spin. | - | `animation_preset.angle` |
| `cloud_layers` | 6 | layers | time | Each layer adds its noise to the world shader and may add a volume the renderer marches; six hold one layer per height band with room to spare. | - | `clouds.layers` |
| `clump_blades` | 400 | blades | time | Blades of one clump are shaped one by one; the triangle budget caps their detail as well. | - | `ground_cover.populations[].params.blades`, `ground_element.params.blades` |
| `clump_size` | 1000 | elements | physical | A thousand elements is a dense tussock or patch; larger groups are populations of their own. | - | `ground_cover.populations[].clumping.per_clump` |
| `cluster_leaves` | 80 | leaves | physical | One spray carries at most about 80 leaves, as a conifer shoot drawn as needle cards. | - | `tree_leaves.clusters.leaves[]` |
| `cluster_variants` | 64 | meshes | memory | Each variant is its own cluster mesh; 64 hide any repeat in a crown. | - | `tree_leaves.variants` |
| `concentration` | 100 | - | physical | A hundredfold concentrate of any liquid preset is already opaque within a millimetre. | - | `material_liquid.concentration` |
| `contact_angle` | 179 | deg | physical | Contact angles lie between complete wetting (0) and none (180); the film thickness needs both ends open. | - | `liquid_fill.spill.contact_angle` |
| `contact_darkening` | 0.36 | - | physical | The darkest soil of the CC0 forest-ground photo is 0.64 of its median; darkening past 0.36 would go below it. | - | `ground_cover.darken` |
| `coordinate` | 200000 | m | physical | A view from a mountain reaches past 100 km; 200 km from the origin holds such a view around a camera anywhere near the centre, and float32 still places a point there within 7.8 mm. | - | `add_camera.location[]`, `add_camera.rotation[]`, `add_camera.target[]`, `add_empty.location[]`, `add_empty.rotation[]`, `add_light.location[]` and 173 more |
| `corner_segments` | 64 | segments | physical | 64 segments round a corner of up to half a turn to within 0.03 % of its radius; more add no visible roundness. | - | `sweep.fillet_segments` |
| `cover_density` | 100000 | 1/m^2 | physical | Elements per square metre: 100 000 is one every 3 mm, past the densest moss or lawn; the instance budget caps the count as well. | - | `ground_cover.populations[].density` |
| `cover_instances` | machine | instances | memory | scene_memory divided by 640 bytes per ground-cover instance: 92 bytes of stored attributes, about 250 bytes of planning arrays and about 300 bytes of render instance. | - | `ground_cover.budget` |
| `cover_share` | 1 | - | physical | A share of the land runs from 0 to 1. | - | (internal) |
| `curve_distance` | 0.95 | - | physical | Raup's D: above 0.95 the generating curve shrinks to a thin sliver far from the axis. | - | `shell.D` |
| `curve_points` | 10,000 | points | protocol | Curve points sent inline as JSON. | - | `curve_from_points.points` |
| `curve_resolution` | 64 | segments | memory | Segments between two points of a smooth curve; with 10 000 points (curve_points) a curve evaluates to 640 000 segments. | - | `curve_from_points.resolution` |
| `cycle_frames` | 2,400 | frames | time | A preset keys every moving bone on every frame of its cycle; 2 400 frames is 100 s at 24 frames a second. | - | `animation_preset.frames` |
| `data_file_bytes` | 268,435,456 | bytes | memory | One JSON data file is read whole into memory and parsed. | - | (internal) |
| `date_length` | 10 | characters | protocol | A date written YYYY-MM-DD. | - | `sky.sun.date`, `weather.sun.date` |
| `density_scale` | 100 | - | physical | Multiplies every population's density; the instance budget caps the count as well. | - | `ground_cover.density_scale` |
| `dents` | 2,000 | dents | time | Dents are pressed one at a time, each visiting the vertices within its reach. | - | `displace_noise.count` |
| `derivation_steps` | 100 | steps | time | Steps of a derivation; growth is capped by lsystem_modules, so 100 serves grammars that grow slowly. | - | `lsystem.iterations` |
| `dial_marks` | 3,600 | marks | time | Each mark is a cutter solid joined into one boolean; 3600 marks divide a dial into tenths of a degree. | - | `engrave_scale.count`, `engrave_scale.classes[].every` |
| `display_gamma` | 5 | - | blender | Blender's display gamma runs up to 5. | - | `camera_setup.gamma` |
| `distance_masks` | 8 | masks | time | Each distance mask measures every candidate point against its objects' surfaces. | - | `ground_cover.populations[].distance` |
| `draco_level` | 10 | - | blender | The glTF exporter's Draco compression levels run from 0 to 10. | - | `export.draco_level` |
| `drips` | 64 | drips | time | Each drip is traced down the outside wall on its own. | - | `liquid_fill.drips.count` |
| `droplet_gravity` | 1000 | - | physical | How fast a droplet speeds up per metre it descends; 4 to 10 is usual, and 1000 already makes every droplet race. | - | `erode.gravity` |
| `droplet_inertia` | 0.99 | - | physical | At 1 a droplet would never turn downhill. | - | `erode.inertia` |
| `droplet_lifetime` | 10,000 | steps | time | Steps one droplet may run. | - | `erode.max_lifetime` |
| `droplets` | 2,000,000 | droplets | time | Each droplet runs up to its lifetime in steps. | - | `erode.droplets` |
| `edge_cuts` | 10 | cuts | memory | Each cut multiplies the faces of a quad by (cuts + 1) squared, so ten cuts make 121 of one; the mesh_vertices check still refuses a result that is too large. | - | `subdivide.cuts` |
| `element_name_length` | 63 | bytes | blender | Blender keeps bone, constraint, shape key and NLA track names to 63 bytes and cuts longer ones, which would then no longer match. | - | `animation_preset.clip`, `animation_preset.bone_map[].bone`, `animation_preset.bone`, `armature_create.bones[].name`, `armature_create.bones[].parent`, `bone_add.bones[].name` and 30 more |
| `element_triangles` | 20,000 | triangles | time | Triangle budget of one ground-cover element; the renderer draws it once per instance, millions of times. | - | `ground_cover.populations[].triangles`, `ground_element.triangles` |
| `element_variants` | 16 | variants | time | Each variant is its own element mesh, built and planned on its own. | - | `ground_cover.populations[].variants` |
| `emission_strength` | 1000 | - | physical | Emission strength of a surface; 1000 outshines any lamp a scene shows beside daylight (a sun of strength 3 to 10). | - | `add_material.emission_strength`, `material_pbr.emission_strength` |
| `erosion_brush` | 1000 | m | memory | The brush lists every grid cell within its radius for each droplet of a batch, (radius / grid spacing) squared cells. 1000 m was the cap before and stays: the schema cannot see the grid spacing, so a spacing-aware check belongs in erode itself (known gap, owned by the landforms job). | - | `erode.radius` |
| `erosion_tiles` | 64 | tiles | memory | Tiles eroded together are held as one float64 grid with copies for the change and the mask; 64 tiles of the largest resolution take about 1 GB per copy. | - | `erode.names` |
| `exposure_stops` | 32 | stops | blender | Blender's scene exposure runs from -32 to 32 stops. | - | `camera_setup.exposure` |
| `exposure_value` | 30 | EV | physical | EV100 far past any lit surface: sunlit snow is about EV 16, and only the sun's own disc is brighter than EV 30. | - | `camera_setup.physical.reference_ev` |
| `extinction_scale` | 20 | - | physical | Twenty times a genus's extinction is past the densest storm cores. | - | `clouds.layers[].density` |
| `f_number` | 128 | - | physical | Large-format lenses stop down to about f/128, the smallest apertures made. | - | `camera_setup.fstop`, `camera_setup.physical.aperture` |
| `face_corners` | 10,000 | corners | time | Corners of one n-gon; Blender triangulates n-gons for drawing and export, slower the larger. | - | `mesh_from_data.faces[]` |
| `fetch` | 1e+07 | m | physical | Open water upwind; 10 000 km spans the widest ocean, far past where a wind sea stops growing. | - | `liquid_body.fetch` |
| `fewest_branch_sides` | 5 | segments | physical | A branch drawn with fewer than five sides shows as a prism. | - | `tree_mesh.ring_segments.min`, `tree_mesh.ring_segments.max` |
| `fewest_growth_rings` | 1 | 1/m | physical | The widest growth rings, of fast-grown poplar or eucalyptus, are a few centimetres; below one ring per metre a board shows no ring at all. | - | `material_layer.wood.ring_density`, `material_procedural.wood.ring_density` |
| `fewest_leaves_per_metre` | 0.1 | 1/m | physical | One leaf per 10 m of leafy branch already leaves the crown bare; a leafless tree takes no tree_leaves call. | - | `tree_leaves.density` |
| `fewest_mask_patches` | 0.01 | 1/m | physical | One wear or dirt patch per 100 m already spans a whole building, the largest surface one layer weathers. | - | `material_layer.mask_scale` |
| `fewest_needles` | 3 | needles | physical | A tuft needs three needles to read as a fan. | - | `material_layer.leaf.needles`, `material_procedural.leaf.needles` |
| `fewest_ring_segments_per_metre` | 1 | 1/m | physical | At one segment per metre of girth every branch thinner than ring_segments.min metres round already gets the fewest segments; fewer would leave even a 30 m giant trunk a coarse polygon. | - | `tree_mesh.ring_segments.per_metre` |
| `fewest_round_steps` | 8 | steps | physical | A circle, an ellipse or a whorl drawn with fewer than 8 steps reads as a polygon. | - | `shell.profile_segments`, `shell.steps` |
| `fewest_sides` | 3 | points | physical | A ring or a closed outline needs at least three points to enclose an area. | - | `add_primitive.segments`, `add_primitive.rings`, `extrude_outline.outline`, `extrude_outline.holes[]`, `lathe.segments`, `loft.sections[].profile` and 4 more |
| `fewest_split_corners` | 4 | corners | blender | Blender triangulates only faces of four or more corners; a triangle needs no split. | - | `add_modifier.triangulate.min_vertices` |
| `fewest_stone_cells` | 0.1 | 1/m | physical | A stone cell or colour patch more than 10 m across is a rock face, built as geometry rather than drawn as a texture cell. | fracture or heightfield | `material_layer.stone.cell_scale`, `material_procedural.stone.cell_scale` |
| `fewest_teeth` | 6 | teeth | physical | Below six teeth the involute flanks undercut away most of each tooth. | - | `gear.teeth`, `sprocket.teeth` |
| `fewest_threads` | 1 | 1/m | physical | The coarsest weaves (sacking, rope mats) have some 100 threads per metre; below one per metre there is no weave left. | - | `material_layer.fabric.threads`, `material_procedural.fabric.threads` |
| `fewest_triangles` | 100 | triangles | physical | Below 100 triangles a tree is a handful of prisms; a card does better. | - | `tree_mesh.lod` |
| `fewest_vein_pairs` | 2 | pairs | physical | A blade with fewer than two vein pairs shows its midrib only, not a leaf. | - | `material_layer.leaf.vein_pairs`, `material_layer.litter.vein_pairs`, `material_procedural.leaf.vein_pairs`, `material_procedural.litter.vein_pairs` |
| `final_resolution` | 4,096 | px | memory | A 4096 px square frame with its float passes and denoiser buffers takes about 1 GB, the pixel guard. | - | `render_final.width`, `render_final.height` |
| `final_samples` | 65,536 | samples | time | Cycles stops converging visibly long before 65 536 samples a pixel; the time limit ends a render first. | - | `render_final.samples`, `render_final.min_samples` |
| `flank_samples` | 24 | points | physical | 24 points draw an involute flank or a roller seat smoother than any render resolves. | - | `gear.tooth_samples`, `sprocket.seat_samples` |
| `focal_length` | 5000 | mm | physical | The longest camera lenses made reach about 5 000 mm, the end of Blender's lens slider. | - | `add_camera.lens`, `camera_setup.focal_length` |
| `forest_band` | 0.5 | - | physical | A switch band of half its distance each way already spans a factor of three in distance. | - | `distant_forest.band` |
| `forest_species` | 6 | species | protocol | Blendworks grows six tree species: oak, birch, pine, willow, maple and olive. | - | (internal) |
| `forest_trees` | 200,000 | trees | memory | Near trees are linked instances (about 300 bytes each) and impostor cards four vertices each; 200 000 of them stay under 100 MB. | - | `distant_forest.budget` |
| `forest_variants` | 12 | trees | time | Each variant is a whole tree that is grown, meshed, leafed and baked into an atlas, several seconds each. | - | `distant_forest.variants`, `distant_forest.sources` |
| `fraction` | 1 | - | physical | A share, weight, mix or colour channel runs from 0 to 1. | - | `abrade.amount`, `abrade.target_convexity`, `add_light.color[]`, `add_material.base_color[]`, `add_material.metallic`, `add_material.roughness` and 320 more |
| `fracture_pieces` | 1,000 | pieces | time | Each piece is cut by exact planes and becomes its own object. | - | `fracture.pieces` |
| `frame` | 1,048,574 | frames | blender | Blender's frame range ends at 1 048 574 (MAXFRAME). | - | `animation_preset.start`, `clip_edit.frame_start`, `clip_edit.frame_end`, `clip_keys.keys[].frame`, `clip_pose.frame`, `render_final.frame` |
| `gear_teeth` | 400 | teeth | physical | Teeth of one gear or sprocket; at 400 a tooth spans under one degree of the pitch circle and reads as a knurl. | - | `gear.teeth`, `sprocket.teeth` |
| `glow_temperature` | 3000 | degC | physical | Molten metals pour below about 3000 degrees Celsius (iron 1538, platinum 1768). | - | `material_liquid.temperature` |
| `grammar_constants` | 64 | constants | protocol | Named numbers of one grammar sent inline. | - | `lsystem.constants` |
| `grammar_name_length` | 32 | characters | protocol | Names of grammar constants, written out in every condition and successor that uses them. | - | `lsystem.constants[].name` |
| `grammar_number` | 1e+09 | - | physical | Numbers in a grammar are lengths, angles, widths and counts; a billion is past them all. | - | `lsystem.constants[].value` |
| `grammar_rules` | 64 | rules | time | Every module of every derivation step is matched against the rules. | - | `lsystem.rules` |
| `grammar_text` | 1,024 | characters | protocol | One axiom or production sent as text. | - | `lsystem.axiom`, `lsystem.rules[]` |
| `graph_links` | 300 | links | protocol | Links one material_nodes call may add. | - | `material_nodes.links` |
| `graph_nodes` | 100 | nodes | protocol | Nodes one material_nodes call may add. | - | `material_nodes.nodes` |
| `grid_side` | 1,414 | vertices | memory | Vertices per side of a square grid: the square root of mesh_vertices. | - | `heightfield.resolution` |
| `half_turn` | 180 | deg | physical | Angles between two directions run from 0 to 180 degrees. | - | `add_light.spot_angle`, `add_modifier.bevel.angle`, `bevel.angle`, `bevel.normal_angle`, `camera_setup.aperture_rotation`, `displace_noise.normal_angle` and 40 more |
| `height_band` | 1e+06 | m | physical | A height mask only selects points; callers write far ends up to 1000 km to mean no bound, past any height the world holds. | - | `ground_cover.populations[].height_range[]`, `scatter.height_range[]` |
| `helix_turns` | 1000 | turns | physical | Coil springs and screw threads have up to a few hundred turns; the segment count is checked against path_points as well. | - | `sweep.helix.turns` |
| `hue_shift` | 0.2 | - | physical | Leaves of one tree vary in hue by at most a fifth of the colour circle either way; more turns green leaves blue or red. | - | `tree_leaves.variation.hue` |
| `ico_subdivisions` | 7 | levels | memory | Each level quadruples the faces of an icosphere; level 7 has 327 680 faces, rounder than any sphere needs. | - | `add_primitive.subdivisions` |
| `ik_chain_bones` | 16 | bones | physical | Limbs chain 2 or 3 bones; 16 covers spines, tails and tentacles. | - | `ik_chain.chain_length` |
| `image_file_bytes` | 536,870,912 | bytes | memory | One image file read from disk. | - | (internal) |
| `image_size` | 8,192 | px | memory | A float RGBA image of 8192 px squared takes 1 GB, the pixel guard. | - | `image_new.width`, `image_new.height` |
| `impostor_frames` | 16 | frames | memory | A 16 by 16 atlas of views is 256 directions, 8 degrees apart over the upper hemisphere. | - | `distant_forest.frames` |
| `impostor_pixels` | 512 | px | memory | Frame size; a 16 by 16 atlas of 512 px frames is 8192 px square, the image limit. | - | `distant_forest.frame_pixels` |
| `impostor_pixels_min` | 16 | px | physical | A view smaller than 16 px loses the crown's outline; cards that small are canopy. | - | `distant_forest.frame_pixels` |
| `index_of_refraction` | 4 | - | physical | Diamond refracts at 2.42 and germanium at about 4, the highest of common materials. | - | `material_liquid.ior` |
| `instances` | 20,000 | instances | time | Each copy is its own Blender object; past 20 000 objects the dependency graph update after every later call slows down. | scatter or ground_cover (instances drawn by the renderer) | `instances.count`, `instances.rotations`, `instances.scales`, `instances.points`, `instances.normals`, `instances.circle.count` and 6 more |
| `iso` | 409600 | - | physical | ISO 409 600 is the top setting of current professional cameras. | - | `camera_setup.physical.iso` |
| `jitter_scale` | 0.99 | - | physical | A random scale change as a share either way; below 1 so that no organ shrinks to nothing. | - | `instances.phyllotaxis.jitter.scale` |
| `jpeg_quality` | 100 | - | physical | The JPEG quality scale ends at 100. | - | `export.jpeg_quality`, `image_save.quality`, `render_preview.quality` |
| `key_value` | 1e+06 | - | physical | A key holds a location in metres, a rotation in degrees, a scale or a shape key value; a million is past the edge of the world (coordinate) and past 2 700 turns. | - | `clip_keys.keys[].value[]` |
| `label_number` | 1e+09 | - | protocol | Numbers printed by a repeat; past a billion they are no longer read as dial or scale labels. | - | `engrave.repeat.number_start`, `engrave.repeat.number_step` |
| `lacunarity` | 8 | - | physical | Past a frequency ratio of 8 the octaves lie so far apart in size that the sum shows separate layers instead of one fractal. | - | `ground_cover.populations[].noise.lacunarity`, `heightfield.lacunarity`, `noise_displace.lacunarity`, `scatter.noise.lacunarity`, `tree_mesh.bark_noise.lacunarity` |
| `land_behind` | 16 | - | physical | Land out of view needs only its silhouette for shadows and reflections; 16 times sparser keeps it. | - | `distant_land.behind` |
| `land_behind_min` | 1 | - | physical | 1 keeps the spacing of the land in view on every side. | - | `distant_land.behind` |
| `land_border_tolerance` | 0.01 | m | physical | Border heights of distant land are taken from the region's own surface; 1 cm covers the ray casts a millimetre inside the border on slopes up to 85 degrees. | - | (internal) |
| `land_detail` | 512 | vertices | memory | At 512 vertices across a ring's inner half size every ring holds about two million triangles, the whole land budget. | - | `distant_land.detail` |
| `land_detail_min` | 8 | vertices | physical | Eight vertices across a ring's inner half size is the coarsest ring that still shows a hill. | - | `distant_land.detail` |
| `land_distance_min` | 80000 | m | physical | Distant land reaches at least 80 km: from a 500 m hill the horizon lies 80 km away, so land that ends sooner shows its edge. | - | `distant_land.distance` |
| `land_memory` | 720,000,000 | bytes | memory | The triangle budget times the bytes per triangle: what the largest land may hold. | - | (internal) |
| `land_triangle_bytes` | 240 | bytes | memory | Per triangle of land: the mesh in Blender (positions, corners, edges, normals, UVs and three attributes, about 110 bytes) and in Cycles (vertices, triangles, normals and BVH nodes, about 130 bytes). | - | (internal) |
| `land_triangles` | 3,000,000 | triangles | memory | Three million triangles take about 1.5 million vertices, under the mesh vertex limit, and about 0.7 GB with the renderer's BVH (land_triangle_bytes), well inside an 8 GB machine. | - | `distant_land.budget` |
| `leaf_aspect` | 1.5 | - | physical | Kidney-shaped leaves such as ginkgo grow up to about 1.5 times wider than long. | - | `ground_cover.populations[].params.aspect`, `ground_element.params.aspect` |
| `leaf_shapes` | 6 | shapes | physical | The leaf preset draws a species' outline in at most six variants. | - | `tree_leaves.shapes` |
| `least_aperture_ratio` | 0.01 | - | blender | Blender's anamorphic aperture ratio starts at 0.01. | - | `camera_setup.aperture_ratio` |
| `least_bake_seconds` | 1 | s | time | Setting up a bake alone takes about a second; a shorter time limit always fails. | - | `bake.time_limit` |
| `least_bake_size` | 16 | px | physical | A baked map smaller than 16 px holds less than the default 16 px margin around one island. | - | `bake.size`, `bake.atlas_sizes[].size` |
| `least_bark_grain` | 1 | - | physical | Bark relief runs along the branch (fissures, ridges, plates) and at 1 it is round; bands around the trunk, such as cherry lenticels, come from the bark material. | - | `tree_mesh.bark_noise.grain` |
| `least_bit_depth` | 8 | bits | blender | Saved images hold 8 bits per channel or more. | - | `image_save.depth`, `render_final.depth` |
| `least_cadence` | 10 | steps/min | physical | One step in six seconds, slower than any walk. | - | `animation_preset.cadence` |
| `least_camera_millimetres` | 1 | mm | blender | Blender's focal lengths and sensor sizes start at 1 mm. | - | `add_camera.lens`, `camera_setup.focal_length`, `camera_setup.sensor_width`, `camera_setup.sensor_height` |
| `least_card_blades` | 2 | blades | physical | A card stands for a group of blades; a single blade is drawn as geometry. | - | `material_layer.grass_blade.card_blades`, `material_procedural.grass_blade.card_blades` |
| `least_card_width` | 0.02 | - | physical | A leaf card at least 2 % as wide as it is long; narrower cards vanish edge-on (pine needles use about 3 %). | - | `tree_leaves.card.width` |
| `least_cavity_voxels` | 16 | voxels | physical | Fewer than 16 voxels across cannot tell a container's wall from its cavity. | - | `liquid_fill.voxels` |
| `least_clump_size` | 1 | elements | physical | A clump holds at least one element. | - | `ground_cover.populations[].clumping.per_clump` |
| `least_contact_angle` | 1 | deg | physical | Contact angles lie between complete wetting (0) and none (180); the film thickness needs both ends open. | - | `liquid_fill.spill.contact_angle` |
| `least_convexity` | 0.5 | - | physical | Volume over convex hull volume of stones and fragments lies above one half; a lower target would be met before the first pass. | - | `abrade.target_convexity` |
| `least_cycle_frames` | 8 | frames | physical | A gait or prop cycle needs about 8 frames to show its contact, passing and lift poses. | - | `animation_preset.frames` |
| `least_display_gamma` | 0.01 | - | physical | Display gamma divides the exponent, so 0 has no meaning; at 0.01 every mid-grey already maps to black (0.5 to the power 100). | - | `camera_setup.gamma` |
| `least_exposure_value` | -10 | EV | physical | EV100 of a moonless, overcast night landscape, the darkest scene a camera records. | - | `camera_setup.physical.reference_ev` |
| `least_extinction_scale` | 0.01 | - | physical | A hundredth of a genus's extinction leaves a faint veil; less draws nothing. | - | `clouds.layers[].density` |
| `least_f_number` | 0.5 | - | physical | f/0.5 is the widest aperture a lens in air can have; the fastest lenses made are about f/0.7. | - | `camera_setup.fstop`, `camera_setup.physical.aperture` |
| `least_iso` | 1 | - | physical | The ISO arithmetic speed scale starts at 1; the slowest films and sensors are near ISO 6 to 50. | - | `camera_setup.physical.iso` |
| `least_letter_spacing` | 0.1 | - | physical | At a tenth of the font's spacing letters already overlap into one blot. | - | `engrave.spacing` |
| `least_manning_n` | 0.01 | s/m^(1/3) | physical | Manning's n of the smoothest channels (glass, finished concrete) is about 0.01. | - | `liquid_body.roughness` |
| `least_metaball_level` | 0.05 | - | blender | Below 0.05 the stiffness (level over 0.42) nears Blender's floor of 0, where a sphere adds no field. | - | `blob.threshold` |
| `least_petals` | 3 | petals | physical | Flowers have at least three petals. | - | `ground_cover.populations[].params.petals`, `ground_element.params.petals` |
| `least_scratch_density` | 0.1 | - | physical | A tenth of the default scratch density leaves a few scattered scratches. | - | `material_layer.worn_metal.scratch_scale`, `material_layer.brass.scratch_scale`, `material_procedural.worn_metal.scratch_scale`, `material_procedural.brass.scratch_scale` |
| `least_shutter` | 1e-06 | s | physical | A microsecond, past the 1/32 000 s of the fastest camera shutters. | - | `camera_setup.physical.shutter` |
| `least_spot_angle` | 1 | deg | blender | Blender's spot cones open at least 1 degree. | - | `add_light.spot_angle` |
| `least_stone_size` | 0.005 | m | physical | Gravel from 5 mm up; finer sediment is sand, which is a texture, not a stone. | - | `shore_stones.size_range[]` |
| `least_talus_angle` | 1 | deg | physical | Below a degree every slope slides and the ground flows flat; real talus stands at 30 to 45 degrees. | - | `erode.talus_angle` |
| `least_wave_cells` | 16 | cells | physical | With fewer than 16 cells a side a wave mesh cannot show crests and troughs. | - | `liquid_body.cells` |
| `least_widening` | 1 | - | physical | A widening factor of 1 leaves an element as it is; below 1 it would narrow it. | - | `ground_cover.populations[].max_widen` |
| `least_width_ratio` | 0.05 | - | physical | A branch thinner than a twentieth of its parent is lost beside it. | - | `lsystem.width_ratio` |
| `length` | 1e+06 | m | physical | Any distance inside the world (its diagonal is 566 km) and beyond it the longest views and visibilities on Earth (near 500 km), with room; cloud fields drift and fade over such distances. | - | `abrade.edge_length`, `add_camera.orthographic_scale`, `add_empty.size`, `add_light.size`, `add_modifier.displace.texture.size`, `add_modifier.weld.distance` and 219 more |
| `length_ratio` | 2 | - | physical | A child more than twice as long as its parent no longer reads as a branch of it. | - | `grow_tree.length_ratio[]`, `tree_leaves.clusters.fork_length` |
| `letter_spacing` | 10 | - | blender | Blender's character spacing runs up to 10. | - | `engrave.spacing` |
| `light_power` | 1e+06 | W | physical | A million watts of light, past any searchlight or stadium mast, where Blender's power slider ends. | - | `add_light.energy` |
| `linear_density` | 1000 | 1/m | physical | Leaves, needles or ring segments per metre: 1000 puts one every millimetre, denser than needles on a twig; the instance and vertex limits cap the result. | - | `tree_leaves.density`, `tree_mesh.ring_segments.per_metre` |
| `lip_flare` | 2 | - | physical | A lip that flares out more than twice the aperture size reads as a separate fan. | - | `shell.lip.flare` |
| `lip_thickening` | 4 | - | physical | A rim more than five times the wall thickness closes the aperture of a small shell. | - | `shell.lip.thicken` |
| `liquid_tilt` | 60 | deg | physical | A sloshing or accelerated liquid surface tilts by atan(a / g); 60 degrees is 1.7 g, past any carried or driven container. | - | `liquid_fill.tilt.angle` |
| `liquid_volume` | 1e+06 | l | physical | A thousand cubic metres, a large storage tank; the container's own capacity is checked too. | - | `liquid_fill.volume` |
| `listed_indices` | 200,000 | indices | protocol | Face, edge or vertex indices sent inline as JSON; larger selections go by facing, box or material, or take the whole mesh. | - | `assign_material.faces`, `bevel.faces`, `bevel.edges`, `displace_noise.faces`, `engrave.faces.faces`, `extrude.faces` and 10 more |
| `listed_names` | 100 | names | protocol | Names one reply lists before it summarises. | - | (internal) |
| `listed_sources` | 64 | meshes | protocol | Source meshes listed inline in one scatter; each is placed in its own pass. | - | `scatter.sources` |
| `lod_levels` | 8 | levels | memory | Each level of detail is a decimated copy of the mesh; game engines use up to 8 (Unreal Engine's import limit). | - | `generate_lods.count`, `generate_lods.ratios`, `generate_lods.distances`, `ground_cover_export.levels` |
| `lod_ratio` | 0.99 | - | physical | A level of detail keeps a share of the triangles of LOD0 and must drop at least 1 % of them, or it is LOD0 again. | - | `generate_lods.ratios[]` |
| `loft_sections` | 256 | sections | protocol | Cross-sections of one loft sent inline as JSON. | - | `loft.sections` |
| `lsystem_modules` | 1,000,000 | modules | memory | Modules of a derived L-system word, each held as a Python tuple. | - | `lsystem.max_length` |
| `manning_n` | 0.2 | s/m^(1/3) | physical | Manning's n of dense brush and timber floodplains reaches about 0.2. | - | `liquid_body.roughness` |
| `map_strength` | 10 | - | physical | A normal or height map at more than ten times its authored strength tilts the shading normals past the horizon and breaks the surface up. | - | `material_pbr.normal_strength`, `material_pbr.height_strength` |
| `mark_classes` | 16 | classes | protocol | Mark classes of one scale listed inline; dials use two to four (minor, half, major). | - | `engrave_scale.classes` |
| `material_offset_min` | -32,768 | slots | blender | Blender's solidify material offset is a signed 16-bit number and starts at -32 768. | - | `add_modifier.solidify.material_offset` |
| `material_slots` | 32,767 | slots | blender | Blender's material slot indices end at 32 767. | - | `add_modifier.solidify.material_offset`, `mesh_from_data.material_indices[]` |
| `mesh_from_data_corners` | 800,000 | corners | protocol | Face corners sent inline as JSON: four for each of mesh_from_data_faces. | import (a mesh file in the workspace) | `mesh_from_data.uvs` |
| `mesh_from_data_faces` | 200,000 | faces | protocol | Faces sent inline as JSON; larger meshes come in through import. | import (a mesh file in the workspace) | `mesh_from_data.faces`, `mesh_from_data.edges`, `mesh_from_data.material_indices`, `mesh_from_data.smooth_faces`, `mesh_from_data.sharp_edges`, `mesh_from_data.creases` |
| `mesh_from_data_vertices` | 100,000 | vertices | protocol | Vertices sent inline as JSON; larger meshes come in through import. | import (a mesh file in the workspace) | `mesh_from_data.vertices`, `mesh_from_data.vertex_uvs` |
| `mesh_vertices` | 2,000,000 | vertices | memory | One generated mesh stays under about 200 MB with its edges, faces, normals and UVs. | - | `add_modifier.triangulate.min_vertices`, `array.count` |
| `metaball_level` | 4 | - | blender | Each sphere's stiffness is the field level over 0.42, so that a lone sphere keeps its radius; Blender caps stiffness at 10. | - | `blob.threshold` |
| `mist_cells` | 1,024 | cells | memory | The low-ground map is a float image of at most 1024 by 1024 cells (4 MB) and as many ray casts. | - | `valley_mist.cells` |
| `mist_cells_min` | 16 | cells | physical | Fewer than 16 cells across cannot hold a valley. | - | `valley_mist.cells` |
| `name_length` | 255 | bytes | blender | Blender 5.2 keeps datablock names (objects, materials, images, collections, actions) up to 255 bytes and cuts longer ones, which would then no longer match. | - | `abrade.name`, `add_camera.name`, `add_empty.name`, `add_empty.parent`, `add_empty.collection`, `add_light.name` and 235 more |
| `names` | 1,000 | names | protocol | Names one call may list; bigger sets go by collection. | collection (where the tool takes one) | `bake.names`, `bake.atlas_sizes[].materials`, `bake.source`, `bone_mirror.bones`, `boolean.cutters`, `collection_create.objects` and 23 more |
| `needles` | 64 | needles | physical | More than 64 needles on one card blur into a solid blade at the size a card is seen. | - | `material_layer.leaf.needles`, `material_procedural.leaf.needles` |
| `node_inputs` | 64 | inputs | protocol | Input values set inline on one node. | - | `material_nodes.nodes[].inputs` |
| `node_settings` | 16 | settings | protocol | Settings set inline on one node. | - | `material_nodes.nodes[].settings` |
| `normal_weight` | 100 | - | blender | Blender's weighted normal strength runs from 1 to 100. | - | `add_modifier.weighted_normal.weight` |
| `normal_weight_threshold` | 10 | - | blender | Blender's weighted normal threshold runs from 0 to 10. | - | `add_modifier.weighted_normal.threshold` |
| `octaves` | 12 | octaves | time | Each octave evaluates the noise once more at every point; at lacunarity 2 the twelfth octave is 2048 times finer than the first, finer than the vertex spacing of any mesh it displaces. | - | `ground_cover.populations[].noise.octaves`, `ground_cover.populations[].noise.warp_octaves`, `heightfield.octaves`, `heightfield.warp_octaves`, `noise_displace.octaves`, `noise_displace.warp_octaves` and 4 more |
| `organ_index` | 1,000,000 | - | physical | Index of the first organ of a phyllotaxis; a sunflower head holds a few thousand florets, so a million covers any part of any spiral. | - | `instances.phyllotaxis.start` |
| `organ_symbols` | 8 | symbols | protocol | Organ symbols of one plant, each placed as its own group of copies. | - | `lsystem.organs` |
| `outline_holes` | 64 | holes | protocol | Hole outlines of one flat plate sent inline as JSON. | - | `extrude_outline.holes` |
| `outline_points` | 4,096 | points | protocol | Points of one flat outline sent inline as JSON. | - | `extrude_outline.outline`, `extrude_outline.holes[]` |
| `pack_margin` | 0.5 | - | physical | uv_pack keeps its margin around every island, so a margin of half the UV square leaves no room for any island. Blender's unwrap and smart project take up to 1 (uv_margin). | - | `uv_pack.margin` |
| `pair` | 2 | items | physical | A path, a sequence or a set to combine needs a start and an end: at least two points, sections, wheels, copies, steps or objects. | - | `add_modifier.screw.steps`, `add_modifier.screw.render_steps`, `array.count`, `curve_from_points.points`, `engrave.curve.waypoints`, `engrave.repeat.count` and 14 more |
| `path_length` | 1,024 | characters | protocol | A file path in a request, relative to the workspace; 1024 characters hold any folder depth a project uses. | - | `export.path`, `ground_cover_export.path`, `image_load.path`, `image_save.path`, `import.path`, `load_blend.path` and 13 more |
| `path_points` | 4,096 | points | memory | Points of one path, sent inline or sampled from an exact circle or helix; with 512 profile points a sweep along it stays near the mesh_vertices limit. | - | `engrave.curve.waypoints`, `instances.waypoints`, `liquid_body.path`, `roller_chain.waypoints`, `sweep.waypoints` |
| `pebble_elongation` | 2 | - | physical | Pebbles up to three times as long as wide, as long river pebbles. | - | `ground_cover.populations[].params.elongation`, `ground_element.params.elongation` |
| `pebble_flatness` | 0.9 | - | physical | At 1 a pebble would be a disc with no thickness; 0.9 is a flat skimming stone. | - | `ground_cover.populations[].params.flatness`, `ground_element.params.flatness` |
| `petals` | 40 | petals | physical | Daisies and asters carry up to about 40 ray florets. | - | `ground_cover.populations[].params.petals`, `ground_element.params.petals` |
| `pipe_exponent` | 3 | - | physical | Measured trees follow the pipe model with exponents from about 1.8 to 3; 3 is Murray's law for vessels. | - | `grow_tree.exponent` |
| `pixel_guard_bytes` | 1,073,741,824 | bytes | memory | Pixels one call may hold in memory at once. | - | (internal) |
| `plan_calls` | 10,000 | calls | time | validate checks each call's schema and names in about a millisecond; 10 000 calls answer within seconds, and a larger plan is checked in parts. | validate the plan in parts | `validate.calls` |
| `plan_problems` | 500 | problems | protocol | Problems one validate answer lists, about 1 MB at most, well inside the MCP line link; the rest are counted. | validate the plan in parts | (internal) |
| `planet_radius` | 1e+08 | m | physical | Far beyond any rocky planet (Earth 6371 km); a larger radius is a flat world. | - | `distant_land.earth_radius` |
| `planet_radius_min` | 100000 | m | physical | A world smaller than 100 km across bends its horizon within a few kilometres; smaller worlds are not landscapes. | - | `distant_land.earth_radius` |
| `populations` | 16 | populations | time | Each population builds its elements and plans its instances over the whole surface. | - | `ground_cover.populations` |
| `power_exponent` | 8 | - | physical | Power-law size spectra in nature have exponents from about -1 to -4; at -8 almost every instance takes the smallest size. | - | `scatter.scale_exponent`, `shore_stones.size_exponent` |
| `pressure_angle` | 35 | deg | physical | Gears are cut at 14.5 to 25 degrees; above 35 the teeth come to a point below the tip circle. | - | `gear.pressure_angle` |
| `preview_bevel_resolution` | 8 | segments | memory | The preview curve bevels every skeleton node; at 8 a tree of 50 000 nodes evaluates to near the mesh_vertices limit. | - | `grow_tree.preview_resolution`, `lsystem.preview_resolution` |
| `preview_resolution` | 1,024 | px | protocol | Previews come back inline as base64; 1024 px keeps a reply under a few MB. | render_final (writes a file of any size) | `render_preview.resolution` |
| `preview_samples` | 64 | samples | time | A preview answers in seconds on a CPU; final renders take more. | render_final | `render_preview.samples` |
| `problems` | 50 | problems | protocol | Problems one call reports, at most about 2 KB each, so a refusal stays near 100 KB however bad the input; the rest are counted as 'and N more'. | fix the problems listed, then check again | (internal) |
| `profile_points` | 512 | points | memory | Points of one cross-section; a sweep makes profile points times path points vertices, and 512 times 4096 path points is about the mesh_vertices limit. | - | `lathe.profile`, `loft.sections[].profile`, `loft.samples`, `shell.points`, `shell.profile_segments`, `sweep.profile` |
| `profile_segments` | 256 | segments | memory | Segments of a preset cross-section: a rounded rectangle with 256 per corner already has about 1000 points, twice profile_points, which a sweep along a full path would build before the vertex check. | - | `loft.sections[].segments`, `sweep.segments` |
| `python_source` | 200,000 | characters | protocol | Source of one run_python call. | - | `run_python.code` |
| `quarter_turn` | 90 | deg | physical | Slopes, elevations and tilts from a plane run up to 90 degrees. | - | `animation_preset.arm_swing`, `animation_preset.heel_angle`, `assign_material.facing_angle`, `bevel.facing_angle`, `displace_noise.facing_angle`, `distant_forest.max_slope` and 34 more |
| `query_page` | 1,000 | items | protocol | Items one reply page lists; use offset for more. | - | `grow_tree.limit`, `lsystem.limit`, `mesh_query.limit`, `tree_skeleton.limit` |
| `rain_rate` | 100 | mm/h | physical | Cloudbursts reach about 100 mm/h; the streak count saturates well before. | - | `weather.rain` |
| `ramp_stops` | 32 | stops | blender | Blender's colour ramp holds at most 32 stops (MAXCOLORBAND). | - | `material_nodes.nodes[].stops` |
| `range_height` | 6000 | m | physical | Mountain ranges rise at most about 6 km above the land at their feet (the Himalaya above the Ganges plain). | - | `distant_land.range_height` |
| `relative_weight` | 1e+06 | - | physical | Weights compare up to a million to one; a source rarer than that never shows among the instances one call places. | - | `scatter.sources[].weight` |
| `relief` | 20000 | m | physical | The largest height difference of real land is about 10 km (Mauna Kea from the sea floor, the Everest massif); twice that leaves room for exaggerated terrain. | - | `add_modifier.displace.strength`, `animation_preset.lift`, `animation_preset.bob`, `atmosphere.base_height`, `atmosphere.ground_fog.thickness`, `clouds.layers[].base` and 32 more |
| `relief_share` | 0.5 | - | physical | A rib, ridge or bark relief deeper than half the local size (aperture or branch radius) would fold the wall over itself. | - | `shell.ribs.height`, `shell.spiral_ridges.height`, `tree_mesh.bark_noise.share` |
| `render_seconds` | 600 | s | time | The render call's default timeout of 900 s less 300 s for scene sync, denoising and writing. | - | `render_final.time_limit` |
| `repeats` | 720 | copies | time | Each copy is laid out and cut on its own; 720 is a mark every half degree around a dial. | - | `engrave.repeat.count` |
| `request_bytes` | 67,108,864 | bytes | protocol | One request line on the bridge pipe. | - | (internal) |
| `ribs` | 64 | ribs | physical | Ribbed shells carry at most a few dozen ribs per whorl or ridges around the aperture. | - | `shell.ribs.count`, `shell.spiral_ridges.count` |
| `rig_roles` | 128 | roles | protocol | Roles of one rig sent inline; a humanoid with every finger has about 60. | - | `animation_preset.bone_map`, `rig_template.landmarks` |
| `rigid_parts` | 256 | parts | protocol | Rigid parts listed inline in one skin_bind call. | - | `skin_bind.rigid` |
| `rings_between_nodes` | 32 | rings | physical | Rings sit about one edge apart; 32 between two skeleton nodes follow any bend, and the vertex check caps the mesh. | - | `tree_mesh.rings_per_segment` |
| `safe_camera_distance` | 16384 | m | blender | Renders flatten meshes into float32 world space; within 16 384 m of the origin that keeps every point within 0.5 mm. A render whose camera stands farther out moves the world so the camera sits near the origin (floating_origin.py). | - | (internal) |
| `scale_factor` | 10000 | - | physical | A scale factor of an object, a copy, a profile or a texture: ten thousandfold turns a millimetre part into a 10 m one, or a 1 m tile into a 10 km one; anything larger is built at its own size. | - | `add_empty.scale[]`, `add_modifier.simple_deform.factor`, `array.relative_offset[]`, `ground_cover.populations[].scale_range[]`, `instances.scale`, `instances.scales[]` and 48 more |
| `scene_info_page` | 1,000 | objects | protocol | Objects one scene_info page lists. | - | `scene_info.limit` |
| `scene_memory` | machine | bytes | memory | Half of the memory this process may use (its container's limit, else the physical memory), measured when the bridge starts; the other half stays for Blender, its undo copy and the renderer. | - | (internal) |
| `scratch_density` | 20 | - | physical | Twenty times the default scratch density already covers a surface as a brushed finish. | - | `material_layer.worn_metal.scratch_scale`, `material_layer.brass.scratch_scale`, `material_procedural.worn_metal.scratch_scale`, `material_procedural.brass.scratch_scale` |
| `screw_steps` | 10,000 | steps | blender | Blender's screw modifier takes at most 10 000 steps per turn and 10 000 turns. | - | `add_modifier.screw.steps`, `add_modifier.screw.render_steps`, `add_modifier.screw.iterations` |
| `search_seconds` | 300 | s | time | A packing or fitting search stops after this many seconds, well inside the longest call the MCP server waits for. | - | `uv_pack.time_limit` |
| `sediment_capacity` | 1000 | - | physical | The capacity factor Kc of droplet erosion is about 1 to 30 in practice; 1000 already strips a slope in one pass. | - | `erode.capacity` |
| `seed` | 2,147,483,647 | - | blender | Blender's random seeds are signed 32-bit integers. | - | `abrade.seed`, `chip.seed`, `clouds.layers[].seed`, `displace_noise.seed`, `distant_forest.seed`, `distant_land.seed` and 55 more |
| `sensor_size` | 200 | mm | physical | Film and sensors up to large format: 8x10 inch sheet film exposes about 200 by 250 mm. | - | `camera_setup.sensor_width`, `camera_setup.sensor_height` |
| `shortest_droplet_step` | 0.001 | m | physical | At 1 mm a step a droplet travels at most 10 m in its longest life (droplet_lifetime), and each step erodes only a step-sized patch; shorter steps carve nothing. | - | `erode.step` |
| `shortest_leaf` | 0.002 | m | physical | The smallest leaves and twigs of forest-floor litter, such as conifer scale leaves, are about 2 mm long. | - | `ground_cover.populations[].params.length[]`, `ground_element.params.length[]` |
| `shortest_leaf_shape` | 0.3 | - | physical | Leaves of one tree differ in length about threefold at most (shade against sun leaves); 0.3 of the card length is the shortest shape. | - | `tree_leaves.shape_length[]` |
| `shortest_lip` | 0.02 | turns | physical | A lip shorter than 2 % of a whorl spans less than one ring at the default 48 steps. | - | `shell.lip.length` |
| `shortest_ray_reach` | 0.001 | m | physical | Occlusion rays shorter than 1 mm darken only creases under a millimetre wide, which no render of a hand-sized part or larger shows. | - | `bake.ao_distance`, `material_layer.distance` |
| `shortest_render_seconds` | 0.01 | s | time | A budget under 10 ms ends before Cycles finishes its first sample pass. | - | `render_final.time_limit` |
| `shortest_search_seconds` | 1 | s | time | A search needs about a second for its first trial. | - | `uv_pack.time_limit` |
| `shortest_shutter_frames` | 0.01 | frames | physical | Below a hundredth of a frame motion blur stays under a pixel for all but the fastest objects. | - | `render_final.motion_blur.shutter` |
| `shortest_side_twig` | 0.1 | - | physical | A side twig under a tenth of its cluster's twig is a stub with no room for its own leaves. | - | `tree_leaves.clusters.fork_length` |
| `shutter` | 60 | s | physical | Cameras time exposures up to 30 s; a minute covers timed night exposures. | - | `camera_setup.physical.shutter` |
| `shutter_frames` | 10 | frames | physical | A shutter open for ten frames already smears a moving object into a streak; film shutters stay below one frame. | - | `render_final.motion_blur.shutter` |
| `side_shoots` | 6 | shoots | physical | Side shoots of a fallen twig. | - | `ground_cover.populations[].params.branches`, `ground_element.params.branches` |
| `simple_check_points` | 6,000 | points | time | The self-crossing check compares every edge with every other; past 6 000 points (36 million pairs) it is skipped. | - | (internal) |
| `size_exponent` | 4 | - | physical | An exponent of a size ratio: at 4 a branch half as thick already bends or shrinks 16 times as much; more makes every thin twig limp. | - | `grow_tree.ratio_power`, `grow_tree.gravitropism.thinness`, `grow_tree.phototropism.thinness`, `grow_tree.gnarl.radius_power`, `grow_tree.wind.profile`, `grow_tree.wind.thinness` |
| `sky_altitude` | 60000 | m | physical | Balloons and high aircraft fly below about 40 km; at 60 km the sky above is black. | - | `sky.altitude` |
| `smallest_arc` | 1 | deg | physical | An arc or a spherical cap under one degree bends from a straight row or a flat disc by less than 0.5 % of its width. | waypoints (a straight row) or phyllotaxis disc mode | `instances.circle.sweep`, `instances.phyllotaxis.polar_extent` |
| `smallest_aspect_ratio` | 0.05 | - | physical | The inverse of aspect_ratio: an ellipse more than 20 times wider than high reads as a slit. | - | `ground_cover.populations[].params.aspect`, `ground_element.params.aspect`, `shell.aspect` |
| `smallest_blade_width` | 0.0002 | m | physical | The finest grass blades, such as fine fescues, are about 0.2 mm wide at the root. | - | `ground_cover.populations[].params.width`, `ground_element.params.width` |
| `smallest_cover_patch` | 0.01 | m | physical | At the densest cover (cover_density, one element every 3 mm) a 1 cm clump or band holds about 30 elements; a narrower one holds too few to read as a clump or a band. | - | `ground_cover.populations[].clumping.radius`, `ground_cover.populations[].shore` |
| `smallest_crumb` | 0.002 | m | physical | Soil crumbs and moss clumps are at least about 2 mm across; finer grains read as a flat colour. | - | `material_layer.moss.clump_size`, `material_layer.soil.clod_size`, `material_procedural.moss.clump_size`, `material_procedural.soil.clod_size` |
| `smallest_curve_distance` | 0.01 | - | physical | Raup's D: below 0.01 the generating curve touches the axis and the whorls fuse into one solid column. | - | `shell.D` |
| `smallest_element_size` | 0.001 | m | physical | A blade or a petal shorter than 1 mm is moss-sized texture, not geometry, and a pebble under 2 mm across is sand on the Wentworth scale. | - | `ground_cover.populations[].params.height[]`, `ground_cover.populations[].params.petal_length`, `ground_cover.populations[].params.size[]`, `ground_element.params.height[]`, `ground_element.params.petal_length`, `ground_element.params.size[]` |
| `smallest_erosion_brush` | 0.01 | m | physical | Droplets model gullies that running water carves, a centimetre wide and more; finer rills are texture. erode widens any brush to 1.5 grid spacings as well. | - | `erode.radius` |
| `smallest_feature_multiplier` | 0.01 | - | physical | At 0.01 every feature of a material preset grows a hundredfold, millimetre grain and pores to decimetres; the preset's own size fields set larger patterns. | - | `material_layer.wood.scale`, `material_layer.worn_metal.scale`, `material_layer.brass.scale`, `material_layer.rust.scale`, `material_layer.stone.scale`, `material_layer.marble.scale` and 28 more |
| `smallest_glow_temperature` | 400 | degC | physical | Below 400 degrees Celsius lava and metal no longer glow; they start to show red near 525 (the Draper point). | - | `material_liquid.temperature` |
| `smallest_instance_scale` | 0.01 | - | physical | Elements are built at their real size; a hundredth turns a 10 cm plant into 1 mm, the smallest_element_size. | - | `ground_cover.populations[].scale_range[]` |
| `smallest_lacunarity` | 1 | - | physical | Each octave is at least as fine as the one before; below 1 the octaves would grow coarser. | - | `ground_cover.populations[].noise.lacunarity`, `heightfield.lacunarity`, `noise_displace.lacunarity`, `scatter.noise.lacunarity`, `tree_mesh.bark_noise.lacunarity` |
| `smallest_organ_scale` | 0.001 | - | physical | A thousandth turns a 1 m organ template into 1 mm, smaller than any bud or stamen a plant model shows. | - | `lsystem.organs[].scale` |
| `smallest_pattern_spacing` | 0.005 | m | physical | The finest bark fissures and turf tufts lie about 5 mm apart; ripples, fissures or tufts packed closer read as plain grain. | - | `material_layer.bark.fissure_spacing`, `material_layer.sand.ripple_spacing`, `material_layer.grass_ground.tuft_size`, `material_procedural.bark.fissure_spacing`, `material_procedural.sand.ripple_spacing`, `material_procedural.grass_ground.tuft_size` |
| `smallest_pipe_exponent` | 1.8 | - | physical | Measured trees follow the pipe model with exponents from about 1.8 to 3; 2 is Leonardo's rule. | - | `grow_tree.exponent` |
| `smallest_plant_part` | 0.0005 | m | physical | Petals, flower discs, stems, base leaves and twigs of ground plants are at least about half a millimetre across. | - | `ground_cover.populations[].params.petal_width`, `ground_cover.populations[].params.centre_radius`, `ground_cover.populations[].params.stem_width`, `ground_cover.populations[].params.leaf_width`, `ground_cover.populations[].params.thickness`, `ground_element.params.petal_width` and 4 more |
| `smallest_pressure_angle` | 5 | deg | physical | Standard gears are cut at 14.5 to 25 degrees; 5 degrees is far below any of them. | - | `gear.pressure_angle` |
| `smallest_preview_resolution` | 64 | px | physical | Below 64 px a preview shows too little of the model to judge. | - | `render_preview.resolution` |
| `smallest_render_size` | 16 | px | physical | Below 16 px a frame shows nothing to judge. | - | `render_final.width`, `render_final.height` |
| `smallest_scale_factor` | 0.0001 | - | physical | The smallest scale factor of a copy or a texture: a 1 m source shrinks to 0.1 mm, below a pixel in any view. | - | `instances.phyllotaxis.scale_by_age.from`, `instances.phyllotaxis.scale_by_age.to` |
| `smallest_size_step` | 0.1 | - | physical | A size factor per branch order below 0.1 shrinks leaves tenfold at each order inward, so they vanish one order in from the twigs. | - | `tree_leaves.size_by_order` |
| `smallest_split_angle` | 1 | deg | physical | Below one degree smart project cuts every curved surface with fewer than 360 segments around into single-face islands. | - | `uv_smart_project.angle_limit` |
| `smallest_sun_size` | 0.05 | deg | physical | The sun is 0.53 degrees wide; at a tenth of that a shadow 10 m behind its edge blurs by under 1 cm, sharper than any real sun shadow. | - | `sky.sun_size` |
| `smallest_texture_feature` | 0.0001 | m | physical | 0.1 mm: finer texture features than this show in no render short of a macro shot. | - | `add_modifier.displace.texture.size` |
| `smallest_texture_repeat` | 0.001 | - | physical | At a thousandth of a repeat the UV square shows 8 pixels of the largest image (image_size); fewer repeats stretch single pixels over the whole surface. | - | `material_pbr.scale[]` |
| `smallest_whorl_expansion` | 1.05 | - | physical | Raup's W: below 1.05 a shell barely widens and needs hundreds of whorls to grow. | - | `shell.W` |
| `smoothing_passes` | 50 | passes | time | Each pass visits every edge of the mesh once; 50 passes spread a weight across a whole limb. | - | `skin_bind.smooth` |
| `spacing_jitter` | 0.49 | - | physical | A shift of up to this share of the even spacing keeps every member between its neighbours; at half the spacing two would meet. | - | `grow_tree.spacing_variation[]` |
| `specific_stiffness` | 1e+12 | m | physical | E / (rho g) of green wood is about 1e6 m and of steel about 3e6 m; 1e12 is rigid at any tree size, so nothing sags. | - | `grow_tree.stiffness` |
| `speed` | 100 | m/s | physical | Speeds of things moving through a scene: the fastest land animals run 30 m/s and race cars reach about 100 m/s. | - | `animation_preset.speed` |
| `spill_area` | 1000 | m^2 | physical | A spill from a cup covers a fraction of a square metre; 1000 square metres is a burst tank. | - | `liquid_fill.spill.area` |
| `spin_turns` | 100 | turns | physical | Turns in one clip; at 100 turns in a 2 s clip a part spins 50 times a second, past what frames can show. | - | `animation_preset.turns` |
| `spray_forks` | 8 | twigs | physical | A leaf spray branches into at most about eight side twigs before it reads as a branch. | - | `tree_leaves.clusters.forks[]` |
| `stem_children` | 200 | branches | physical | A stem carries at most a couple of hundred side branches; max_nodes caps the whole tree. | - | `grow_tree.branches[]` |
| `stem_levels` | 4 | levels | physical | Weber and Penn build a tree from at most four stem levels, trunk to twigs; leaves come after. | - | `grow_tree.levels` |
| `stem_segments` | 200 | nodes | physical | 200 nodes bend one stem more smoothly than any render shows; max_nodes caps the whole tree. | - | `grow_tree.segments[]` |
| `stone_classes` | 8 | classes | time | One set of stone meshes is built for each class (fracture, chip, abrade); eight steps from angular to round are finer than the eye tells apart. | - | `shore_stones.classes` |
| `stone_group_density` | 10 | 1/m^2 | physical | Groups of shore stones come at most ten to the square metre, past which their stones overlap into one bed. | - | `shore_stones.cluster_density` |
| `stone_size` | 100 | m | physical | The longest side of the largest boulders of a shore (rock fall blocks, glacial erratics) is tens of metres. | - | `shore_stones.size_range[]` |
| `stone_variants` | 8 | meshes | time | Meshes built for each class; eight give a shore no two alike next to each other. | - | `shore_stones.variants` |
| `stones_per_group` | 1000 | stones | time | A mean of a thousand stones in a group is a talus slope; each stone is placed and thinned against its neighbours. | - | `shore_stones.per_cluster` |
| `subdivision_levels` | 6 | levels | blender | Blender subdivides at most 6 levels in a modifier; each level quadruples the faces. | - | `add_modifier.shrinkwrap.subsurf_levels` |
| `sun_intensity` | 10 | - | physical | Ten times the physical sun disc already overexposes any shot by several stops. | - | `sky.sun_intensity` |
| `sun_size` | 10 | deg | physical | A sun disc twenty times its true width reads as a lamp, not the sun. | - | `sky.sun_size` |
| `swelling` | 4 | - | physical | A trunk base, root or branch collar swells to at most five times its own radius, as the buttresses of tropical trees. | - | `tree_mesh.flare.amount`, `tree_mesh.root_flare.amount`, `tree_mesh.collar` |
| `symbol_length` | 1 | characters | protocol | A module symbol is one letter. | - | `lsystem.organs[].symbol` |
| `talus_angle` | 89 | deg | physical | The tangent of the talus angle sets the stable height step; at 90 degrees it is infinite. | - | `erode.talus_angle` |
| `texel_density` | 100000 | px/m | physical | 0.01 mm per pixel, finer than any texture an asset needs. | - | `uv_pack.texel_density`, `uv_smart_project.texel_density`, `uv_unwrap.texel_density` |
| `text_length` | 2,000 | characters | memory | Text objects are built glyph by glyph; a page of text is the most a label needs. | - | `engrave.text`, `text_object.text` |
| `text_size` | 10000 | m | blender | Blender's text size ends at 10 000. | - | `text_object.size` |
| `texture_contrast` | 5 | - | blender | Blender clamps a built-in texture's contrast to 0..5. | - | `add_modifier.displace.texture.contrast` |
| `texture_depth` | 30 | levels | blender | Blender's built-in noise textures take at most 30 detail levels. | - | `add_modifier.displace.texture.depth` |
| `texture_frequency` | 10000 | 1/m | physical | Features per metre of a procedural texture; 10 000 per metre is 0.1 mm, the smallest_texture_feature. | - | `material_layer.mask_scale`, `material_layer.wood.ring_density`, `material_layer.stone.cell_scale`, `material_layer.fabric.threads`, `material_procedural.wood.ring_density`, `material_procedural.stone.cell_scale` and 1 more |
| `texture_intensity` | 2 | - | blender | Blender clamps a built-in texture's brightness to 0..2. | - | `add_modifier.displace.texture.intensity` |
| `texture_size` | 8,192 | px | memory | The same pixel guard as image_size. | - | `uv_info.texture_size`, `uv_pack.texture_size`, `uv_smart_project.texture_size`, `uv_unwrap.texture_size` |
| `thermal_sweeps` | 20,000 | sweeps | time | Each thermal sweep visits every cell of the grid. | - | `erode.iterations` |
| `thickness_clamp` | 100 | - | blender | Blender's solidify clamp factor runs from 0 to 100. | - | `add_modifier.solidify.thickness_clamp` |
| `thinnest_wire` | 0.25 | px | physical | A wireframe line under a quarter pixel covers too little of any pixel to show after filtering. | - | `render_final.wire_width` |
| `tile_index` | 1,000 | tiles | physical | A thousand tiles each way of 100 m tiles reach 100 km, half the coordinate range. | - | `heightfield.tile[]` |
| `time_length` | 12 | characters | protocol | A clock time written HH:MM:SS.sss. | - | `sky.sun.time`, `weather.sun.time` |
| `tip_leaves` | 12 | leaves | physical | A twig tip carries at most about a dozen leaves, as the whorl of a horse chestnut. | - | `tree_leaves.tip_leaves` |
| `tip_sprays` | 8 | clusters | physical | At most about eight shoots fan out of one twig tip; more merge into one ball of leaves. | - | `tree_leaves.clusters.per_tip` |
| `tree_nodes` | 50,000 | nodes | time | Skeleton nodes of one tree or L-system; growth, radii and the mesh walk every node, and 50 000 is a large tree down to its twigs. | - | `grow_tree.max_nodes`, `grow_tree.offset`, `lsystem.max_nodes`, `lsystem.offset`, `tree_skeleton.offset` |
| `tree_points` | 50,000 | points | time | Attraction points of space colonization; every growth step searches them against the nodes. | - | `grow_tree.points`, `grow_tree.roots.points` |
| `triangle_budget` | 2,000,000 | triangles | memory | 2 million triangles hold about 1 million vertices, half the mesh_vertices limit, leaving room for the junction work. | - | `tree_mesh.lod` |
| `tropism_bend` | 100 | - | physical | The turtle turns by e /H x T/ radians after each step; at 100 it already turns fully towards T in one step, so a larger e or T changes nothing. | - | `lsystem.tropism.vector[]`, `lsystem.tropism.strength` |
| `tropism_weight` | 4 | - | physical | A tropism vector of length 4 already outweighs the unit growth direction fourfold; longer ones point every step straight along it. | - | `grow_tree.tropism[]`, `grow_tree.phototropism.direction[]`, `grow_tree.roots.tropism[]` |
| `turn` | 360 | deg | physical | One full turn; more repeats the same orientation. | - | `armature_create.bones[].roll`, `bone_add.bones[].roll`, `bone_constraint.min[]`, `bone_constraint.max[]`, `bone_edit.bones[].roll`, `clouds.layers[].wind_direction` and 20 more |
| `turn_segments` | 512 | segments | physical | Steps around a turned part; at 512 steps a chord leaves the true circle by less than 0.002 % of the radius, so more steps add no visible roundness. | - | `add_primitive.segments`, `add_primitive.rings`, `lathe.segments`, `shell.steps`, `tree_mesh.ring_segments.min`, `tree_mesh.ring_segments.max` |
| `twilight_depth` | 20 | deg | physical | Twilight ends when the sun is 18 degrees below the horizon; 20 covers all of it. | - | `sky.sun.elevation`, `weather.sun.elevation` |
| `utc_offset` | 14 | h | physical | Time zones run from UTC-12 to UTC+14. | - | `sky.sun.utc_offset`, `weather.sun.utc_offset` |
| `uv_coordinate` | 1000 | - | physical | UVs a thousand tiles out still place a texel of an 8192 px texture within half a texel in float32. | - | `material_pbr.offset[]`, `mesh_from_data.uvs[][]`, `mesh_from_data.vertex_uvs[][]` |
| `uv_margin` | 1 | - | blender | Space between islands as a share of the UV square; Blender's unwrap, smart project and pack take margins up to 1. | - | `uv_smart_project.island_margin`, `uv_unwrap.margin` |
| `vacuum_ior` | 1 | - | physical | Nothing refracts less than vacuum, index 1. | - | `material_liquid.ior` |
| `variation` | 0.95 | - | physical | A seeded change of a size or length, up to this share either way; at 100 % a varied size would reach zero. | - | `grow_tree.length_variation[]`, `grow_tree.taper`, `tree_leaves.jitter.size`, `tree_leaves.clusters.spacing_variation`, `tree_leaves.variation.size`, `tree_leaves.variation.saturation` and 1 more |
| `vein_pairs` | 40 | pairs | physical | Leaves carry up to about 30 pairs of lateral veins (beech, hornbeam, chestnut). | - | `material_layer.leaf.vein_pairs`, `material_layer.litter.vein_pairs`, `material_procedural.leaf.vein_pairs`, `material_procedural.litter.vein_pairs` |
| `view_cameras` | 8 | cameras | time | Every candidate point is tested against the view of each camera. | - | `ground_cover.cameras` |
| `view_margin` | 2 | - | physical | A margin of twice the frame on every side covers what a panning camera swings past. | - | `ground_cover.view_margin` |
| `volume_bounces` | 128 | bounces | time | Each bounce traces one more scattering event per path; past 128 clouds grow no brighter and renders only take longer. | - | `clouds.bounces` |
| `wall_gap` | 0.01 | m | physical | The gap between a liquid and its glass only separates the two surfaces for refraction; wider than 1 cm it shows as an air layer. | - | `liquid_fill.gap` |
| `wave_cells` | 512 | cells | time | The wave field is summed from the spectrum at every vertex; 512 cells a side is 263 000 vertices. | - | `liquid_body.cells` |
| `wave_distortion` | 20 | - | physical | Past a distortion of 20 a wave texture's rings or bands tear into plain noise. | - | `material_layer.wood.ring_distortion`, `material_procedural.wood.ring_distortion` |
| `whorl_branches` | 12 | branches | physical | Conifers set at most about a dozen branches in one whorl. | - | `grow_tree.whorl[]` |
| `whorl_expansion` | 100 | - | physical | Raup's W: coiled snails, ammonites and the nautilus lie between 1.1 and 10; 100 reaches the flaring forms of limpets and ears. | - | `shell.W` |
| `whorl_translation` | 20 | - | physical | Raup's T: tall spires reach about 10; 20 leaves room for needle-like towers. | - | `shell.T` |
| `whorls` | 24 | turns | physical | The most whorled real shells, the turritellids, have about 20 whorls; the path_points limit still caps whorls times steps. | - | `shell.turns` |
| `widening` | 4 | - | physical | Widened past fourfold, a far blade reads as a smear. | - | `ground_cover.populations[].max_widen` |
| `wind_speed` | 40 | m/s | physical | Wind at 10 m height; the wave spectra used (JONSWAP, Pierson-Moskowitz) are fitted to winds up to a severe storm of about 40 m/s. | - | `liquid_body.wind.speed` |
| `winding` | 36000 | deg | physical | An angle that may wind round, such as a screw, a twist along a path, a helix start or a dial's range: 100 turns, more than any part winds; the vertex limit still caps the mesh it makes. | - | `add_modifier.screw.angle`, `add_modifier.simple_deform.angle`, `engrave.cylinder.angle`, `engrave.ring.angle`, `engrave_scale.ring.angle`, `engrave_scale.cylinder.angle` and 10 more |
| `wire_width` | 32 | px | physical | Lines 32 px wide already hide the faces between edges in a full-size frame; the default is one pixel. | - | `render_final.wire_width` |
| `world_strength` | 1000 | - | physical | A world or sky strength multiplies the environment's light; 1000 lifts the dimmest HDRI or a night sky far past full daylight. | - | `set_world.strength`, `set_world_hdri.strength`, `sky.strength` |
| `zero_tolerance` | 0.01 | m | physical | A distance under which a height or an offset counts as zero; past 1 cm it would erase real detail such as bevels, chamfers and engraving. | - | `clean_mesh.tolerance` |
