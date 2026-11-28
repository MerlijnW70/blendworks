# Meadow structure: sources and measurements

Job `meadow-structure`. The contract is the "Meadow structure" section of `docs/DESIGN.md`; this page lists what it is built on, which values are taken from sources and which are chosen, and what the tests measure.

## Why

The lake example rendered as a carpet: the same grass, height, colour and density up to the water line, and a flat green ground beyond the cover. A real meadow has structure at every scale, from tussocks and seed heads at a metre to moisture and soil over tens of metres, and that structure is what a photograph of a meadow shows.

## Sources

| Id | Source | Used for |
|---|---|---|
| M1 | K. J. Beven, M. J. Kirkby, "A physically based, variable contributing area model of basin hydrology", Hydrological Sciences Bulletin 24 (1979) 43-69 | The topographic wetness index `ln(a / tan β)` behind moisture |
| M2 | T. G. Freeman, "Calculating catchment area with divergent flow based on a regular grid", Computers & Geosciences 17 (1991) 413-422 | Upslope area routed to every lower neighbour in proportion to slope^1.1 |
| M3 | A. M. Heimsath, W. E. Dietrich, K. Nishiizumi, R. C. Finkel, "The soil production function and landscape equilibrium", Nature 388 (1997) 358-361 | Soil depth: thicker in convergent hollows, thinner on convex crests |
| M4 | W. Tobler, "Three presentations on geographical analysis and modeling", NCGIA Technical Report 93-1 (1993) | The hiking function `6 e^(-3.5 \|s + 0.05\|)` km/h that paths minimise |
| M5 | D. Helbing, J. Keltsch, P. Molnár, "Modelling the evolution of human trail systems", Nature 388 (1997) 47-50 | Later paths follow trodden ground, so trails merge into a network |
| M6 | D. N. Cole, "Experimental trampling of vegetation. I. Relationship between trampling intensity and vegetation response", Journal of Applied Ecology 32 (1995) 203-214 | Trodden ground loses height and cover first, then turns bare |
| M7 | P. B. Adler, D. A. Raff, W. K. Lauenroth, "The effect of grazing on the spatial heterogeneity of vegetation", Oecologia 128 (2001) 465-479 | Patch grazing: a mosaic of short lawns and rejected tall patches |
| M8 | M. H. Andrew, "Grazing impact in relation to livestock watering points", Trends in Ecology & Evolution 3 (1988) 336-339 | Grazing and trampling heavier near water (the piosphere) |
| M9 | H. Ellenberg, H. E. Weber, R. Düll, V. Wirth, W. Werner, D. Paulißen, "Zeigerwerte von Pflanzen in Mitteleuropa", Scripta Geobotanica 18 (1991); M. O. Hill, J. O. Mountford, D. B. Roy, R. G. H. Bunce, "Ellenberg's indicator values for British plants", ECOFACT 2 (1999) | Moisture values F of the drifting species |
| M10 | P. J. Clark, F. C. Evans, "Distance to nearest neighbor as a measure of spatial relationships in populations", Ecology 35 (1954) 445-453 | The aggregation index R the drift test measures |
| M11 | M. L. Gorman, R. D. Stone, "The Natural History of Moles", Christopher Helm (1990) | Molehills: domes of loose soil a few decimetres across, thrown up in runs where the soil is deep and not waterlogged |
| M12 | J. S. Rodwell (ed.), "British Plant Communities, Volume 3: Grasslands and montane communities", Cambridge University Press (1992) | Mesotrophic grassland (MG5 hay meadow, MG10 rush pasture): tussocks and sedges on wet ground, shorter swards where grazed |

## Values

**From sources.** The wetness index (M1) on Freeman's routing (M2); soil deepening with convergence (M3); Tobler's function (M4); the trail discount (M5, a half here, chosen); the Ellenberg F values of the drifting species (M9): oxeye daisy *Leucanthemum vulgare* 4, black knapweed *Centaurea nigra* 5, buttercups *Ranunculus acris* and *R. repens* 6 and 7 (7 used, the drifts of the damper ground), ragged robin *Lychnis flos-cuculi* 8, lawn daisy *Bellis perennis* 5; the yellow flowers of `dry_steppe` take 3.

**Chosen, and stated.** Every response range and value is in `bridge/blendworks_bridge/cover_presets.py`; the field coefficients are in `meadow_fields.py` and the "Meadow structure" section of `docs/DESIGN.md`. The ones that set the look:

- Short grass is shorter where grazed (1.7 to 0.5 times over grazing 0.15 to 0.85), on thin soil (0.75 at none) and dry ground (0.75), and on trodden ground (0.5); a grazed sward is denser than a rank one (0.45 to 1 over grazing 0 to 0.8, M7), and it thins on drought-prone and waterlogged ground, in deep shade and on paths (to 0.1).
- Tussocks of tall grass grow where grazing is light and the ground moist (M12), and ripen there: seed heads are 0.08 of the short grass's blades and 0.3 of the tall grass's on average, from a quarter to 1.75 times that by ripeness.
- Trodden patches: one per 2000 m², 1.5 to 4 m in radius; paths: a tread of 0.3 m either side of the centreline, a worn verge to 1.2 m.
- Drifts: one per 80 m², radii of 1.5 to 5 m (daisies), 2 to 6 m (buttercups), 1.5 to 4 m (knapweed), 1 to 3 m (ragged robin); strays 4 % of the density outside them.
- Molehills: at most 0.012 per m² (120 per hectare), in runs of 6 within 3 m, on soil deeper than 0.25 and moisture below 0.92 (M11).
- Moss: up to 120 tufts per m² of 1.5 to 4 cm, where moisture passes 0.4 and shade 0.15.

**Colours.** The ground's green and straw are those of `docs/research/ground-cover.md` (measured on a CC0 meadow photograph), seen from afar as the whole canopy: green `[0.05, 0.11, 0.025]`, straw `[0.2, 0.165, 0.075]`, moss `[0.035, 0.07, 0.015]`, bare soil `[0.09, 0.065, 0.04]`.

## Measurements

The tests in `bridge/tests/test_meadow_fields.py`, `test_meadow_cover.py` and `test_meadow_ground.py` measure:

- **Fields.** On grids with the same plan and seed, so the noise cancels: a valley floor gains more moisture than its flanks (by more than 0.15) and more downstream than upstream; a hollow is wetter (by more than 0.2) and deeper-soiled than a hump; moisture near a lake rises over the dry ground by more than 0.2 within 5 m of the shore, less at 10 to 15 m and under 0.1 at 25 to 30 m; a crown shades the ground along the sun (shade over 0.6) and dampens it, not the sunny side.
- **Variation.** In each 20 m square of a 60 m meadow, 2 m cells of short grass differ by at least 1.5 times in mean height and 1.4 times in density (90th over 10th percentile).
- **Drifts.** Daisies and buttercups have a Clark-Evans R under 0.6 (a random pattern of the same count is over 0.9); at least 80 % of flowers have a nearest neighbour of their own species; buttercups stand on ground 0.15 moister than daisies.
- **Paths.** Between two points round a 14 m hill the path's mean grade is under half the straight line's and under 0.6 times that of random lines; paths reach the water; the tread is bare (disturbance over 0.9) and the short grass on it under a fifth of its density elsewhere.
- **Moss.** In damp shade moss is more than five times as dense as in dry sun, the cover as a whole more than 1.5 times, and the grass in dry sun more than 0.25 straw-er.
- **Tiling.** The largest autocorrelation of the baked ground's detail at shifts of 16 pixels or more stays under 0.35 on planes of 3, 30 and 300 m (texels of 2.3 cm, 23 cm and 2.3 m), for the whole material and for the meadow layer alone, while the same measure of a texture repeated four times across is over 0.8.
- **Mid distance.** On a 300 m tile with a lake, the ground's colour over the dry land, blurred over 9 m, varies at least twice as much (coefficient of variation) with the fields as without, and is darker where it is moister (correlation under -0.3).
