# Woodland structure: stands, edges and understorey

Sources and the values the `woodland` tool takes from them (job `woodland-edges`). Each rule names the module that
implements it.

## Spacing of stems

- **Competition makes stands regular at short range.** Stems in a closed stand keep apart because crowns and roots
  compete; point-process models fitted to forest stands are hard-core and soft-core processes at the tree scale and
  cluster processes at larger scales (Stoyan and Penttinen 2000, "Recent applications of point process methods in
  forestry statistics", Statistical Science 15:61–78). `woodland_pattern.inhibit` is the simple sequential inhibition
  process (Diggle 2003, *Statistical Analysis of Spatial Point Patterns*, 2nd ed., section 5.4): a candidate stem is kept
  when it stands at least `spacing (r_i + r_j)` from every stem kept before it, `r` the crown radii. Mature trees use
  0.72 (forest) to 0.75 (copse) of the summed radii, so neighbouring crowns overlap by about a quarter, as crowns of a
  closed stand interlock; young trees 0.5 and saplings 0.35 against everything kept before, since smaller trees grow
  in the gaps and margins of the larger ones; groves 1.05 (open-grown crowns that barely touch) and hedgerow standards
  2.4 (a standard tree every few crown widths along the hedge).
- **Measures.** Clark and Evans' aggregation index R (Clark and Evans 1954, Ecology 35:445–453) is the mean
  nearest-neighbour distance over its expectation `0.5 / sqrt(lambda)` under complete spatial randomness: 1 random,
  below 1 clustered, above 1 regular, 2.149 hexagonal. `woodland_measure.interior_regularity` measures it on the mature
  stems at least a mantle width inside the rim with every mature stem as a neighbour, so the rim adds no edge effect.
  Natural and managed mature stands are mildly regular, R about 1.1 to 1.5 (Pommerening 2002, "Approaches to quantifying
  forest structures", Forestry 75:305–324); the tests ask for at least 1.15. Besag's `L(r) - r` (Besag 1977) with the
  translation edge correction (Ohser and Stoyan 1981) is below 0 where a pattern is regular at distance r and above 0
  where it is clustered; `woodland_pattern.besag_l`. The variance-to-mean ratio of quadrat counts is 1 for a Poisson
  pattern and above 1 for a clustered one (Greig-Smith 1983, *Quantitative Plant Ecology*); `quadrat_dispersion`.
- **Stands are clusters.** Copses scattered over an area (`kind: copses`) have centres from a Poisson process thinned to
  a least gap of 2.5 copse radii, Matérn's second hard-core process (Matérn 1960, *Spatial Variation*), on dry ground of
  gentle slope; copse radii vary log-normally by about a third. Herbs and ferns spread clonally and come in Thomas
  clusters (Thomas 1949, Biometrika 36:18–25): parents at density / per clump, children at Gaussian offsets.

## Sizes and ages

- **de Liocourt's law.** In balanced uneven-aged stands the number of trees falls geometrically from one size class to
  the next larger by a constant quotient q (de Liocourt 1898; Meyer 1952, "Structure, growth, and drain in balanced
  uneven-aged forests", Journal of Forestry 50:85–92, with q about 1.2 to 2 per diameter class). The woodland has three
  classes, saplings, young and mature, in counts `q^2 n`, `q n` and `n`; q defaults to 1.6, so 19 % of the trees are
  mature, 31 % young and 50 % saplings. The mature trees fill the stand by competition; the young and saplings are then
  drawn until their class reaches its count or the space runs out, and the reply gives the measured shares against the
  expected ones.
- **Heights.** Mature trees are 0.8 to 1.1, young trees 0.4 to 0.65 and saplings 0.13 to 0.3 of the species' preset
  height, uniform within the class; shrubs 0.65 to 1.1 of theirs.
- **Young trees are not small copies.** Under competition a young tree grows up before it spreads, and its crown reaches
  nearly to the ground: the crown radius scales with the height share to the power 1.25 and the clear bole with the power
  1.5 (`woodland_species.grown_settings`); the growth step, influence and kill distances shrink with the square root of
  the share (at most to a half) and the attraction points with the crown area. Levels species lose first branches in
  proportion to the share.

## Species by moisture and light

Each species has an Ellenberg indicator value for light L and moisture F (Ellenberg, Weber, Düll, Wirth, Werner and
Paulißen 1991, *Zeigerwerte von Pflanzen in Mitteleuropa*, Scripta Geobotanica 18): oak L7 Fx, birch L7 Fx, Scots pine
L7 Fx, white willow L5 F8, sycamore maple L4 F6, hazel L6 Fx, hawthorn L7 F4, elder L7 F5, grey sallow L7 F9; olive is
not a Central European species and is given L8 F3 for a dry, sunny place. A site's light runs from L3 at the deep
interior to L8.5 at the rim (falling over 12 m into the stand, `woodland_edges.LIGHT_DEPTH`), and its moisture from F3.5
on dry rises to F9 at the water: the moisture index is the larger of `exp(-d / 15 m)`, d the distance to the nearest
water, and the lowness of the ground under the mean of its surroundings 40 m away (a topographic position index, full
at 3 m below; `woodland_site`). Each species weighs a site by a Gaussian about its values (widths 1.6 in L, 1.4 in F;
indifferent species a broad 3.5 about F5.5), and each plant draws its species in proportion.

## The edge

A woodland edge in open country is a sequence of belts (Dierschke 1974, *Saumgesellschaften im Vegetations- und
Standortsgefälle an Waldrändern*, Scripta Geobotanica 6): a fringe (Saum) of tall herbs in front of a mantle (Mantel) of
shrubs, then young trees under the overhanging canopy of the stand. Guidance for structured edges asks for a fringe of a
few metres and a shrub mantle of about 5 to 10 m in front of the trees (for example Coch 1995, *Waldrandpflege*). The
defaults are a 4 m fringe, a 6 m mantle and a 10 m transition; every layer's density is its peak density times a smooth
profile of the signed distance d to the rim (`woodland_edges`):

| Layer | Profile |
|---|---|
| tall herbs | rise from d = -fringe - 2 to d = -fringe/2, fall to 8 % from d = -0.5 to 0.6 mantle |
| shrubs | rise from d = -0.75 fringe to 0.5 m, full in the mantle, fall to 12 % over the transition |
| saplings | rise from d = -1 to 1.5 m, fall to 30 % over the transition |
| young trees | rise over the first half mantle, fall to 50 % one transition behind it |
| mature trees | rise from 0.2 to 0.9 mantle widths in (forest; copse 0.15 to 0.8) |
| ferns | rise from 0.3 mantle to mantle plus half the transition |

The rim itself wanders by a seeded noise (3 m over 30 m by default), so no stand ends on a straight line.

## Canopy and the ground under it

Light under a canopy falls with the leaf layers it passes, `I / I0 = exp(-k LAI)` (Monsi and Saeki 1953). The canopy
cover of `woodland_canopy` treats each crown as a layer of opacity o over a disc of its crown radius (softened over its
outer fifth): cover `= 1 - prod(1 - o)`, with o 0.85 for mature broadleaves, 0.65 birch, 0.75 pine, 0.8 willow, 0.7
young trees and 0.4 saplings, and 0.8 for shrubs. The cover goes on the ground as the float point attribute `meadow_canopy`, the canopy input of the meadow fields.
Where it closes the ground material gets leaf litter over the soil (cover 0.12 to 0.65) and moss in patches in deep shade
(0.5 to 0.95), and ground-cover populations read it: grass thins with `attribute: {name: meadow_canopy, range: [0.9, 0.1]}`.
