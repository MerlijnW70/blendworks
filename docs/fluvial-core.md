# Fluvial core

`fluvial_terrain` builds the first terrain stage: a range lifted by rock uplift and cut by rivers, with lakes and hillslopes, at 30–60 m cells over tens of kilometres. Every step runs on the terrain kernels (`docs/terrain-core.md`); the Python modules only orchestrate them.

| Module | What it holds |
|---|---|
| `fluvial_fields` | uplift fields (block, range, tilted, dome, a user array), lithology bands, weak belts along strike, critical-angle noise |
| `fluvial_model` | one model step and the law it follows |
| `fluvial_spinup` | the coarse-to-fine schedule, the time-step rule and the steady-state stop |
| `fluvial_measure` | Strahler order, flow paths, Hack's exponent, pits, aspect, grid bias, local relief, drainage density, hillslope length |
| `fluvial_presets` | the three presets and the cited ranges they lie in |
| `fluvial_run` | a run from settings: law, fields, spin-up, output grids, rivers, lakes and measures |
| `fluvial_mesh` | terrain tiles with point attributes and shared normals, and the `.npz` archive |
| `commands/fluvial_terrain.py` | the command |

## The model

One step of `dt` years (Braun & Willett 2013, Geomorphology 180–181:170–179):

1. **Lake routing.** D8 receivers, the breadth-first queue and lake routing by the basin graph in carving or filling mode (Cordonnier, Bovy & Braun 2019). This graph gives the lakes, their depths and spill points, and the undrained-pit count.
2. **Flow for incision.** D-infinity directions (Tarboton 1997, `bw_dinf`) on the surface filled by Priority-Flood with epsilon (Barnes et al. 2014): each cell sends its flow to the one or two neighbours that bracket its true downslope direction, shared by angle, so channels follow the slope and not the eight grid directions. On the filled surface every cell descends strictly to the base level, so the graph has no cycle; for incision, a lake fills to its spill point and its flow crosses at the sill, whatever the lake mode. The drainage area is accumulated over the shares.
3. **Uplift.** The surface rises by `U dt`; the base-level cells stay at 0.
4. **Incision.** Implicit stream power for n = 1 over the D-infinity graph (`bw_incise_many`): `h = (h* + sum F_j h_j) / (1 + sum F_j)`, `F_j = K dt A^m w_j / d_j`, cells solved after their receivers. It acts on channel cells only: a cell is a channel when `A (S / 0.6)^2 >= A_c`, the head area at a gradient of 0.6 shrinking on steeper ground as Montgomery & Dietrich 1992 found (`A S^2` about constant). With `flow: d8`, or n other than 1, the incision follows the lake-routed D8 receivers instead.
5. **Hillslopes.** Linear diffusion, or non-linear diffusion with a critical gradient (Roering, Kirchner & Dietrich 1999) by ADI with Picard iterations, the flux ratio capped at 0.999 of the critical one.
6. **Channel export.** Channels are detachment-limited with more transport capacity than the hillslopes supply (Whipple & Tucker 2002): hillslope material that reaches a channel cell is carried away, so the hillslope processes may lower a channel cell but never raise it. Without this rule, channel slopes stand 5 to 17 times above the steady-state law.
7. **Threshold hillslopes.** Where uplift outpaces soil transport, hillslopes are cut back by landsliding to a critical angle (Burbank et al. 1996; Montgomery 2001). The surface is lowered to `min(h, u)`, `|grad u| = tan(angle)` from the cells that keep their heights, solved by fast marching (Sethian 1996, `bw_threshold`), which is isotropic where a path cost over eight neighbours would give octagons. The angles are drawn afresh every step as seeded multi-scale noise down to two cells, between the preset's bounds (30–38 degrees for the young alpine preset); weak rock takes the lower half of the range. Every step ends on its own threshold surface (`test_every_step_ends_on_its_own_threshold_surface`).

The per-cell erosion record adds `lifted - result` every step; with the uplift it closes the mass balance exactly (`test_the_erosion_record_closes_the_mass_balance`). For single receivers, channel slopes at steady state follow `S = (U/K) A^-m` within 1 % median (`test_steady_channels_follow_the_analytic_slope_area_relation`, which runs `flow: d8` because the analytic relation is written for one receiver per cell).

**Base level.** `base_level` names world sides, +Y north. The kernels count rows from their own north (row 0), which is the world's south, so world north is the kernels' south edge; `fluvial_model.WORLD_EDGES` holds the mapping.

## Why the flanks are planar at this stage

A channel keeps pace with rock uplift only where `K A^m S >= U`. On threshold ground, `S` is at most the critical gradient, about 0.7, so channels need `A >= (U / (K S_c))^(1/m)`. For the young alpine preset (`U` = 7 mm/yr, `K` = 1.2e-5, `m` = 0.45) that is (0.007 / (1.2e-5 x 0.7))^2.22, about 3 km^2. Smaller channels cannot incise as fast as the ground rises, so the steady state of detachment-limited stream power at this relief has kilometre-long threshold flanks between valleys draining more than a few km^2; a smaller channel-head area does not change it (it only adds channels on the mask that cannot cut down). In real young ranges the dense, steep low-order network comes from debris-flow incision on channels steeper than about 0.1–0.2 (Stock & Dietrich 2003, Water Resources Research 39(4):1089; 2006, GSA Bulletin 118:1125–1148), a process the stream-power law does not hold. Debris-flow incision and the multi-scale amplification stage (gullies, breaching, scree) are the next stages; this stage delivers the range, its trunk valleys and their network above a few km^2.

## Spin-up

`fluvial_spinup.default_schedule(side)` halves the grid down to 512 cells a side. For 2048 cells the levels are 512, 1024 and 2048.

- **Start.** The coarsest level starts from a surface tilted away from the base level by 5e-4, with 30 m of smooth seeded relief at wavelengths of a third of the domain and more, and 2 m of seeded cell-scale relief, so every cell drains from the first step and the network has long-wavelength structure. A finer level starts from the coarser surface, resampled bilinearly, with 1 cm of random relief to break the ties of the interpolation.
- **Time steps.** The implicit scheme is stable at any step; `dt` only sets how far a knickpoint moves per step: `dt = c dx / (K_max A_max^m S^(n-1))`, `c` counting cells (`fluvial_spinup.stable_dt`), at most 100 kyr. The coarsest level seeks the steady state, which for n = 1 does not depend on `dt`, so it takes `c = 150`; finer levels take `c = 30`. Every level reports the range of steps it took.
- **Budget and stop.** The coarsest level gets 200 steps, middle levels 20, the finest 5. A level stops early once the surface changes by less than 1 % of the uplift per step, the mean over the moving cells. Slope-dependent channel heads and the threshold drawn afresh every step keep the surface fluctuating, so preset runs end on their budget; their last change is reported.
- **Scale.** A level coarser than the physical valley spacing `L_c = (D/K)^(1/2m)` (Perron, Kirchner & Dietrich 2008) raises the diffusivity until `L_c` spans 4 cells, and its head area is at least 8 cells, for the hillslopes and channels the grid cannot resolve.

## Outputs

The command returns the measures, river paths and lakes, and builds `tiles x tiles` mesh objects `name_i_j` that share their edge rows, with UVs continuous over the domain, normals taken from the whole height grid so no seam shows (`test_tiles_share_their_edge_normals_so_no_seam_shows`), and these float point attributes:

| Attribute | Meaning |
|---|---|
| `height` | height in metres |
| `drainage_area` | log10 of the D-infinity drainage area in m^2 |
| `channel` | 1 on channel cells (the slope-dependent head criterion), else 0 |
| `strahler` | Strahler order of the network (drainage area at least 1 km^2), 0 off it |
| `lake_depth` | water depth of the routed lakes in metres |
| `erosion` | height removed during the run, negative where material was laid down |

Drainage area, channels, Strahler orders, flow paths and rivers come from the D-infinity graph the incision follows; orders and paths use each cell's main receiver, the one taking the larger share. `path` also writes every grid (`height`, `drainage_area`, `receivers` (the main receivers), `channel`, `strahler`, `lake_depth`, `erosion`, and `cell`) to a `.npz` archive in the workspace. `rivers` lists the largest rivers as world points from source to mouth, ready for `liquid_body` with `kind: river` and `path`; `lakes` gives each lake's level, centre, area and depth for `liquid_body` lakes. `scatter` reads the attributes as density masks (`density_mask: ["attribute"]`, `attribute: "channel"`). `lods` makes levels of detail of every tile with `generate_lods`, and `horizon` continues the range with `distant_land` out to that distance (`test_scatter_masks_liquids_lods_and_the_horizon_read_the_result`).

## Measures

- **Network.** Strahler orders and Hack's law are counted on cells that drain at least 1 km^2: channel heads lie at 0.1–1 km^2 (Montgomery & Dietrich 1988), so every counted cell is on a channel.
- **Hack's exponent.** `L ~ A^h` (Hack 1957) over the network cells with at least twice that area: the median longest flow path in each of 24 logarithmic area bins, fitted by least squares in log-log; the fit reports the decades of area it spans.
- **Undrained pits.** Cells other than the base level that drain nowhere after lake routing.
- **Aspect share.** Of the cells steeper than a gradient of 0.05, the share whose downslope direction points into the eastern half-plane (+X); the northern half-plane share is reported too.
- **Grid bias.** For each grid direction (0, 45, 90 and 135 degrees) the gradient energy per degree within 2 degrees of it over the energy per degree from 4 to 12 degrees away; the largest of the four. About 1 on a surface without grid bias whatever its regional grain; ridges, channels and planes along the grid make a spike. Tests fail above 1.25.
- **Local relief.** The median height range in 10 km windows, crest to valley floor, the measure Montgomery & Brandon 2002 use.
- **Drainage density and hillslope length,** measured on the channel mask: channel length per land area, and the median flow distance from a ridge cell (a hillslope cell nothing drains into) to the first channel cell. Natural hillslopes are about 100–500 m long (Roering, Perron & Kirchner 2007; Hurst et al. 2012) and alpine drainage densities a few to tens of km/km^2 (Tucker & Bras 1998). At this stage the mask is denser than the incised valleys: channels below a few km^2 lie on the threshold flanks without cutting them (see above).

## Presets

| Preset | Uplift | Rate (m/yr) | K | m | D (m^2/yr) | Critical gradient / threshold angles | Head area at gradient 0.6 (m^2) | Base level |
|---|---|---|---|---|---|---|---|---|
| `young_alpine` | range, crest at the middle, 30 % variation along it; weak belts along strike halfway up each flank (K x 4) | 7e-3 | 1.2e-5 | 0.45 | 5e-3 | 1.25 / 30–38 deg | 1e4 | north and south |
| `mature_mountain` | range, 20 % variation | 5e-4 | 2e-5 | 0.45 | 1e-2 | 1.25 / 28–35 deg | 3e4 | north and south |
| `dissected_plateau` | block with tapered margins, three rock bands (factors 0.3, 1, 0.6) | 2e-4 | 1e-5 | 0.45 | 1e-2 | 1.25 / 26–33 deg | 1e5 | all sides |

Every value lies in a cited range (`fluvial_presets.RANGES`, `LIST_RANGES`, `SETTING_UPLIFT`; `test_every_preset_parameter_lies_in_its_cited_range`): uplift 1–12 mm/yr for young ranges (Burbank et al. 1996; Dadson et al. 2003) and 0.01–1 mm/yr below the threshold relief (Montgomery & Brandon 2002); K 1e-7–1e-4 and weak-rock contrasts of 2–100 (Stock & Montgomery 1999); m 0.35–0.65 (Whipple & Tucker 1999; Kirby & Whipple 2012); D 0.001–0.02 m^2/yr (Roering et al. 1999; Hurst et al. 2012); critical gradient 1.0–1.5 (Roering et al. 1999); threshold angles 24–40 degrees (Burbank et al. 1996; Montgomery 2001); channel heads 1e3–1e6 m^2 (Montgomery & Dietrich 1988, 1992). The young alpine uplift and erodibility set its local relief of about 2.3–2.8 km (crest to valley floor in 10 km windows, the 2.5–4 km of young orogens in Montgomery & Brandon 2002); heights are never scaled. `fluvial_presets.SOURCES` holds the full references.

## Speed and targets

`bench/fluvial/bench.py` runs the young alpine preset and the same range with base level on one side at 2048 x 2048 cells of 30 m (61 km) on 4 threads. `test_fluvial_speed.py` guards the time: a fixed run over the calibration workload must stay within 4 times the ratio in `bench/fluvial/speed-calibration.json`; host noise of ±50 % moves that ratio by at most 3 times.

<!-- fluvial bench -->
Measured on Windows 11 with the host's other work at about 95 % load, 2048 x 2048 cells of 30 m, 4 threads:

| Run | Wall time (s) | Trunk order | Hack's exponent (decades) | Pits | Aspect east / north | Grid bias | Local relief (m) | Drainage density on the mask (km/km^2) | Hillslope length on the mask (m) |
|---|---|---|---|---|---|---|---|---|---|
| young alpine (base level north and south) | 108.1 | 4 | 0.545 (2.18) | 0 | 0.500 / 0.495 | 1.04 | 2292 | 19.7 | 212 |
| young alpine, base level on the south side | 96.4 | 4 | 0.563 (2.84) | 0 | 0.492 / 0.350 | 0.95 | 2520 | 21.7 | 240 |

Targets: 120 s on 4 threads holds; no undrained pit; Hack's exponent 0.5–0.6 over at least 1.5 decades holds; the aspect east share 0.50 ± 0.05 holds (the north share of the one-sided run follows its tilt to the south base level). The trunk reaches order 4, not 6: below the critical area of about 3 km^2 the stream-power channels do not incise (see "Why the flanks are planar"), so the branches that would raise the order are threshold planes; order 5 was reached before the threshold hillslopes were enforced every step. Debris-flow incision is the stage that adds them.
<!-- end fluvial bench -->
