# Rock realism: sources and measured ranges

Job `rock-realism`. The owner found the shore stones of the lake example smooth and "almost alien": pillow shapes, no
surface relief, one uniform grey and a plastic sheen. This page lists where every number of the fix comes from.

## Granite measured as a petrographer would

Granite is two sizes of interlocking mineral grains: feldspar crystals of 4.5 mm in a groundmass of 1.6 mm quartz,
biotite and feldspar grains. `test_granite_has_the_grain_size_colour_index_and_contrast_of_granite` renders fresh granite
(rind, lichen and moss off) from above at 0.39 mm per pixel and measures its colour: each pixel a light, middle or dark
mineral by its luminance against the median, the grain size as 1.5 times the mean lineal intercept (Fullman 1953), the
colour index as the share of dark minerals, and the contrast as the 90th over the 5th percentile of luminance. It reads a
grain of 3.9 mm (the IUGS medium-grained class is 1 to 5 mm), a colour index of 0.12 (granite 0.05 to 0.20) and a contrast
of 13 (pale feldspar over near-black biotite, at least 3), with a mean albedo of 0.25.

## Literature

- **Grain sizes and composition.** Igneous rock is fine grained under 1 mm, medium 1 to 5 mm and coarse above, and granite
  is leucocratic, with a colour index of mostly 5 to 20 % (Le Maitre et al. 2002, the IUGS classification); quartz makes 20
  to 60 % of its light minerals (Streckeisen 1976). Here quartz is 22 % of the rock and biotite 12 %. Sand is 0.0625 to
  2 mm (Wentworth 1922).
- **Colours.** In the USGS Spectral Library 7 (Kokaly et al. 2017) feldspars are pale (visible reflectance above 0.3),
  quartz is clear, so it reads grey in a rock, and biotite and basalt are near black (under 0.1); sandstone is buff to red
  (0.15 to 0.45) and limestone pale (0.3 to 0.55). Granite's plagioclase is 0.33, its orthoclase pinkish at 0.29, quartz
  0.14, biotite 0.03; sandstone 0.23, limestone 0.41 and basalt 0.05. Dry rock is rough: its roughness is set at 0.8 to
  0.96, and the wet test holds dry rock's specular light under a quarter of wet rock's.
- **Beds.** Laminae are under 1 cm thick, thin beds 3 to 10 cm (Campbell 1967); sandstone uses 6 mm and 6 cm.
- **Solution pits** on limestone are millimetres to centimetres across (Ford and Williams 2007); 8 mm here, 12 % cover.
- **Wet rock.** A water film darkens a rough surface of albedo A to `(1 - Re) A (1 - Ri) / (1 - A Ri)` with `Re` 0.066 and
  `Ri = 1 - (1 - Re) / n^2` for water, `n` 1.33 (Lekner and Dorf 1988): albedo 0.1 keeps 0.52 of itself, 0.3 keeps 0.57.
  The shore and weather wetting of the bridge darken by 0.45 and halve the roughness; the test requires at most 0.65 (0.25
  keeps 0.56).
- **Lichen growth.** Crustose thalli widen at a steady rate once established (Armstrong and Bradwell 2010, a review of
  lichenometry), so a surface colonised over time carries colonies of every size up to the oldest: radius proportional to
  an age drawn uniformly. Colonies merge where they meet; their margins are lobed. Cover is stated by the `lichen` amount.
- **Roundness.** Wadell (1932): the mean radius of the corners over the radius of the largest inscribed circle. Powers
  (1953): very angular 0.12 to 0.17, angular to 0.25, subangular to 0.35, subrounded to 0.49, rounded to 0.70. Image and
  visual estimates of one grain differ by several hundredths (Blott and Pye 2008), and a sharp corner of an outline sampled
  at 360 steps reads about 0.1, so the class ranges are Powers' bands widened: talus 0.10 to 0.42, shore 0.30 to 0.62,
  river 0.45 to 0.85.
- **Sphericity and flatness.** Krumbein's intercept sphericity `(b c / a^2)^(1/3)` (1941); flatness `c / a` (Sneed and
  Folk 1958). Fragments are blocky with about six faces and eight corners (Domokos et al. 2020, Plato's cube).
- **Abrasion.** Rounding is fast at first and slow later (Kuenen 1956); curvature-driven flows wear edges and corners first
  while flat faces stay (Firey 1974; Domokos and Gibbons 2012).

## Relief and budget

The relief displaces only where it changes what a pixel sees: through a 35 mm lens on a 36 mm sensor a 1920 px frame
covers 0.54 mm per metre of distance, so 2 mm of relief spans 0.7 px at 5 m and 0.25 px at 15 m. Cycles keeps the diced
triangles; a 256 px render of a granite boulder grew Cycles' memory by 44 MB for 249 000 estimated triangles, 177 bytes
each, so the 6 million triangle budget is about 1.1 GB, inside the judge's 8 GB with the rest of a scene.
