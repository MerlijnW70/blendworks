# Terrain core for photographic mountains — research summary (2026-11-27)

Saved by the coordinator from the research agent's report (the agent could not write files). Full text with all links is in the session transcript; key points:

## Best known solution: three layers
1. Large scale, simulated: uplift field cut by implicit stream power (Braun & Willett 2013, O(n)/step), lake routing (Cordonnier, Bovy, Braun 2019 basin MST), hillslope diffusion (non-linear, Roering 1999; ADI), glacial stage (Hergarten 2021 swath rule: width ∝ Q_ice^0.6, 1.7–2.7x a fluvial step) — gives dendritic drainage obeying Hack's law, ridge hierarchy, U troughs, hanging valleys. Refs: Cordonnier 2016 CGF, Schott 2023 ToG, Tzathas 2024 CGF, Cordonnier 2023 ToG (glacial).
2. Middle scale: multi-scale erosion amplification (Schott 2024 ToG; MIT code H-Schott/MultiScaleErosion): x2 levels with fluvial + thermal (noise-varied talus 30–38°) + deposition, fractal hardness, multi-scale breaching -> 30–100 m cells to 2–4 m with gullies, scree, fans, valley fills.
3. Small scale: gradient-aligned detail below ~4 m + Cycles adaptive-subdivision displacement; flow/wear/deposit/talus masks drive materials and scatter (as Gaea/World Machine/Houdini).

## Why landforms failed
- Speed: 1.2–2.1 ms CPU per cell vs ~7.8 µs (Tzathas numba) / ~0.25 µs per cell per step (serial C++ Braun–Willett, Barnes 2018).
- Strahler order <= 4: domain layout (outlets on all borders limit stream length per Hack's law), not physics -> larger domain, base level on 1–2 edges.
- V valleys: SIA gives narrow V erosion (Cordonnier 2023 §7.2) -> Hergarten swath.
- Clay facets / comb: fixed talus angle (Cordonnier 2016 Fig.17), constant hardness (Schott 2024 Fig.9), single-scale one-cell incisions -> amplification + noisy hardness.
- Current noise+droplet render: no uplift prior (Galin 2019 §4.3.3).

## Decisions
CPU-first Rust core (judge is CPU-only; CPU analytical solver ~parity with GPU at 1024²; GPU solvers lack lake routing). Write kernels from papers (FastScapeLib GPL-3.0, Badlands LGPL/GPL; Schott code MIT as reference). Braun–Willett implicit + coarse-to-fine spin-up as engine. Learned DEM-trained generators excluded (no downloaded data).

## Jobs
- J0 Rust kernels: BFS receiver queue with levels, D8/MFD, accumulation, Cordonnier 2019 basin-MST lake routing, Priority-Flood+eps + flats, implicit stream power, ADI diffusion. Target: stream-power step <= 0.5 µs/cell single-thread at 2049²; integer outputs bit-identical Win/Linux.
- J1 Fluvial core: 2048² at 30 m (61 km) <= 120 s CPU on 4 threads; zero pits; Hack 0.5–0.6 over >= 1.5 decades; trunk order >= 6 at 60 km with base level on one edge; aspect share 0.50±0.05; dendritic clay hillshade.
- J2 Glacial swath: median valley exponent b >= 1.5 on glaciated trunks; hanging steps; hypsometric mode within ±300 m of ELA; <= 3x fluvial step.
- J3 Multi-scale amplification on visible tiles: 8x8 km at 4 m <= 150 s CPU; breach volume <= 0.1 m; seams < 1 cm; slope mode 30–40°; talus 30–38°.
- J4 Render detail + masks: no visible grid at 2–200 m; masks drive materials/scatter/liquids; < 8 GB.
- J5 Planner + composition: domain from Hack's law, base level edges, uplift templates, coasts, three shots pass measures and visual judge.

Reuse from landforms branch: landform_measure (+known-answer tests), landform_references ranges, Barnes flat resolution, basin spanning-tree logic, landform_strata, LOD/surface/region code with seam tests, 3-seed workflow. Drop: landform_glacial/ice_section (SIA), fixed-angle threshold_failure, numpy Kahn solvers, per-preset process modules in the core path, range-tuning. Keep droplet erode for small assets/rocks.
