# Bank form: sources and stated ranges

Job `bank-form`. The owner found the near terrain "too round": smooth noise with no breaks. Real ground is cut and worn by
processes; this page lists the processes Blendworks now models and where every number comes from.

## River banks (`bank_form.py`, applied by every river carve)

- **Bankfull and the water.** At mean flow a river fills about 0.4 to 0.5 of its bankfull depth (Leopold and Maddock
  1953; Williams 1978). A carving river now runs `1 / 0.45 - 1 = 1.22` of its depth below the ground of its line, so its
  banks stand that high above the water (before: 0.15 of the depth, banks of a few centimetres).
- **Bends.** Flow is thrown to the outside of a bend, scours a pool there and cuts the outer bank; the inside builds a
  point bar (Leopold and Wolman 1960; Knighton 1998, Fluvial Forms and Processes). Bank erosion is strongest for a radius of
  curvature of two to three channel widths and fades out by about ten (Hickin and Nanson 1984). The bend intensity runs
  from 1 at two widths to 0 at ten, from the signed curvature of the river path averaged over one width.
- **Cut bank.** The outer bank face steepens with the intensity from the 1:2 of a straight reach to 85 degrees; the pool
  deepens by up to half the depth and the thalweg shifts towards the outer bank by up to 0.3 of the half width.
- **Point bar.** The inner bed rises steadily from the pool to the water's edge and on as a bar at 8 degrees on a gentle
  bend to 3 degrees on a sharp one (point-bar surfaces slope a few degrees, Bridge 2003), over one channel width, then
  up to the floodplain at 17 degrees; the bar is classed gravel.
- **Slumps.** Cut banks fail in slumps and topples whose blocks rest at the toe (Thorne 1990): a Poisson number of 0.12
  per metre of bank with intensity above 0.5, each 0.6 to 1.5 m long, the bank top dropping by up to 45 % of the bank
  height over a retreat of 0.3 to 0.8 m, with a debris heap at the toe.
- **Undercut lip.** On bends with intensity above 0.6 and banks at least 0.3 m above the water the root-bound top layer
  (0.2 to 0.5 m thick, Thorne 1990) overhangs the face: a separate closed mesh 0.2 to 0.45 m thick, 0.12 to 0.35 m over the water, its edge ragged by up to 60 % of the reach where turf blocks broke away and sagging at the tip by a third of it.
- **Stage benches.** Banks that are not cut keep steps 0.1 m high within 0.6 m above the water (Knighton 1998): a flat
  tread over three quarters of each step.

## Hillslopes (`ground_form.py`, `heightfield` with `form: worn`)

- **Slope failure.** Soil and regolith stand at most at their angle of internal friction, 30 to 38 degrees (Selby 1993);
  34 degrees is used. The threshold-hillslope kernel lowers steeper ground to that angle; cells lowered by more than 1 cm
  are bare scars.
- **Rills.** Drainage area from D8 flow over the pit-filled surface (the native kernels). Overland flow cuts a channel
  where the stream power `A^0.5 S` passes a threshold (Montgomery and Dietrich 1988, 1994): 1.2 m^0.5 here; the cut deepens
  by 5 cm per unit above it, at most 0.3 m, the largest depth still called a rill (Poesen et al. 2003).
- **Tussocks.** Tussock grasses such as *Deschampsia cespitosa* form hummocks 0.2 to 0.5 m across and 0.1 to 0.3 m high,
  half a metre to a metre apart (Davy 1980): on 55 % of the sites of a 0.75 m lattice, radius 0.10 to 0.25 m, height 0.08
  to 0.25 m, on slopes under 20 degrees; skipped where a hummock would span fewer than three grid cells.
- Every form fades out over the outermost six cells of a tile, so neighbouring tiles still meet.

## Micro-relief (`ground_relief.py`, displaced by `render_final`)

The standard deviation of the ground's centimetre relief by surface class:

| Class | Value | Source |
|---|---|---|
| turf | 15 mm | stated: the roots, litter and small tussocks of a sward stand a centimetre or two |
| bare soil | 8 mm | random roughness of untilled soil, 4 to 10 mm (Zobeck and Onstad 1987) |
| gravel | 20 mm | gravel-bed surfaces, 10 to 30 mm (Aberle and Nikora 2006) |
| mud | 4 mm | smooth fine sediment, a few millimetres |

A fractal field of features from 8 cm down to a centimetre is scaled to unit deviation (its measured deviation is 0.0624)
and to the class value. It displaces the ground within 15 m of the camera, fading out by 45 m (2 cm spans 0.7 px of a
1920 px frame at 18 m), and only bends the normal beyond. Adaptive subdivision dices it within six million triangles;
the estimate caps each triangle at the frame, the visible ones at three frames and the hidden ones at six (each at the
offscreen dicing scale), so a camera standing on the ground does not count millions of pixels.
