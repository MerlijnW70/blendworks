"""Data table of ground cover presets.

The values and their sources are listed in docs/research/meadow-structure.md."""
PATCHES = {"scale": 9.0, "octaves": 3, "hurst": 0.6, "threshold": 0.42, "softness": 0.35, "seed": 11}
GAPS = {"scale": 6.0, "octaves": 3, "hurst": 0.6, "threshold": 0.3, "softness": 0.4, "seed": 5}
STONY = {"scale": 4.0, "octaves": 2, "hurst": 0.6, "threshold": 0.55, "softness": 0.3, "seed": 23}


def respond(field, affects, between, values):
    return {"field": field, "affects": affects, "range": list(between), "values": list(values)}


TRODDEN = respond("disturbance", "density", (0.35, 0.85), (1.0, 0.1))
BARE = respond("disturbance", "density", (0.15, 0.6), (1.0, 0.0))
GRAZED_SHORT = respond("grazing", "height", (0.15, 0.85), (1.7, 0.5))
EATEN = respond("grazing", "density", (0.4, 0.95), (1.0, 0.25))
SHADED_OUT = respond("shade", "density", (0.4, 1.0), (1.0, 0.35))
FLOWER_SHADE = respond("shade", "density", (0.3, 0.8), (1.0, 0.1))
DRY_BY_MOISTURE = respond("moisture", "dryness", (0.1, 0.45), (0.7, 0.0))
DRY_BY_SOIL = respond("soil", "dryness", (0.0, 0.4), (0.25, 0.0))
UNDER_CANOPY = respond("shade", "density", (0.05, 0.6), (0.2, 1.0))
MOSS_PARAMS = {"blades": 40, "height": [0.015, 0.04], "width": 0.0012, "lean": 50.0, "curvature": 0.6, "spread": 0.03, "dry_tips": 0.3, "dry_length": [0.3, 0.6], "color": [0.03, 0.09, 0.012], "dry_color": [0.15, 0.27, 0.04]}

MEADOW = [
    {"name": "short_grass", "element": "grass", "density": 110.0, "params": {"blades": 16, "height": [0.08, 0.22], "spread": 0.04, "curvature": 0.55, "lean": 24.0, "dry_tips": 0.2, "seed_heads": 0.08}, "slope": [0.0, 42.0], "avoid": 0.06,
     "responses": [TRODDEN, SHADED_OUT, respond("moisture", "density", (0.85, 1.0), (1.0, 0.6)), respond("grazing", "density", (0.0, 0.8), (0.45, 1.0)), respond("moisture", "density", (0.05, 0.35), (0.5, 1.0)), GRAZED_SHORT, respond("soil", "height", (0.0, 1.0), (0.75, 1.2)),
                   respond("moisture", "height", (0.05, 0.5), (0.75, 1.1)), respond("disturbance", "height", (0.1, 0.6), (1.0, 0.5)), DRY_BY_MOISTURE, DRY_BY_SOIL,
                   respond("grazing", "maturity", (0.2, 0.8), (0.6, 0.0))]},
    {"name": "tall_grass", "element": "grass", "density": 22.0, "clumping": {"radius": 0.9, "per_clump": 14.0}, "params": {"blades": 26, "height": [0.35, 0.8], "spread": 0.06, "curvature": 0.65, "lean": 26.0, "dry_tips": 0.4, "dry_length": [0.15, 0.5], "seed_heads": 0.3}, "noise": PATCHES, "slope": [0.0, 35.0], "avoid": 0.12,
     "responses": [respond("grazing", "density", (0.3, 0.75), (1.0, 0.1)), BARE, respond("moisture", "density", (0.1, 0.5), (0.5, 1.0)), SHADED_OUT,
                   respond("soil", "height", (0.0, 1.0), (0.8, 1.2)), respond("moisture", "height", (0.1, 0.6), (0.8, 1.15)), respond("moisture", "dryness", (0.1, 0.45), (0.6, 0.0)),
                   respond("grazing", "maturity", (0.0, 0.6), (0.9, 0.3))]},
    {"name": "sedges", "element": "sedge", "density": 6.0, "clumping": {"radius": 0.6, "per_clump": 6.0}, "slope": [0.0, 30.0], "avoid": 0.12,
     "responses": [respond("moisture", "density", (0.55, 0.85), (0.03, 1.0)), BARE]},
    {"name": "daisies", "element": "flower", "density": 4.0, "clumping": {"radius": 0.7, "per_clump": 10.0}, "params": {"height": [0.3, 0.55], "petals": 21, "petal_length": 0.019, "petal_width": 0.0075, "centre_radius": 0.008, "petal_color": [0.85, 0.85, 0.8], "centre_color": [0.7, 0.45, 0.02]}, "slope": [0.0, 30.0], "avoid": 0.1,
     "drift": {"moisture": 4.0, "radius": [1.5, 5.0]}, "responses": [BARE, EATEN, FLOWER_SHADE, respond("grazing", "height", (0.4, 0.9), (1.0, 0.6))]},
    {"name": "buttercups", "element": "flower", "density": 3.0, "clumping": {"radius": 0.8, "per_clump": 8.0}, "params": {"height": [0.35, 0.65], "petals": 5, "petal_length": 0.014, "petal_width": 0.013, "cup": 40.0, "petal_color": [0.75, 0.55, 0.01], "centre_color": [0.5, 0.45, 0.02]}, "slope": [0.0, 30.0], "avoid": 0.1,
     "drift": {"moisture": 7.0, "radius": [2.0, 6.0]}, "responses": [BARE, FLOWER_SHADE, respond("grazing", "height", (0.4, 0.9), (1.0, 0.6))]},
    {"name": "knapweed", "element": "flower", "density": 1.6, "clumping": {"radius": 0.6, "per_clump": 5.0}, "params": {"height": [0.4, 0.75], "petals": 26, "petal_length": 0.016, "petal_width": 0.003, "cup": 55.0, "centre_radius": 0.007, "petal_color": [0.35, 0.1, 0.42], "centre_color": [0.25, 0.08, 0.3]}, "slope": [0.0, 30.0], "avoid": 0.1,
     "drift": {"moisture": 5.0, "radius": [1.5, 4.0], "share": 0.7}, "responses": [BARE, EATEN, FLOWER_SHADE]},
    {"name": "ragged_robin", "element": "flower", "density": 2.0, "clumping": {"radius": 0.6, "per_clump": 6.0}, "params": {"height": [0.3, 0.6], "petals": 5, "petal_length": 0.015, "petal_width": 0.004, "cup": 20.0, "centre_radius": 0.003, "petal_color": [0.62, 0.17, 0.33], "centre_color": [0.4, 0.1, 0.2]}, "slope": [0.0, 25.0], "avoid": 0.1,
     "drift": {"moisture": 8.0, "radius": [1.0, 3.0], "share": 0.6}, "responses": [BARE, FLOWER_SHADE]},
    {"name": "fallen_leaves", "element": "leaf", "density": 18.0, "under": 6.0, "params": {"color": [0.2, 0.11, 0.04]}, "responses": [UNDER_CANOPY]},
    {"name": "thatch", "element": "grass", "density": 60.0, "params": {"blades": 18, "height": [0.06, 0.2], "curvature": 0.9, "lean": 55.0, "spread": 0.05, "width": 0.004, "dry_tips": 1.0, "dry_length": [0.7, 1.0], "color": [0.14, 0.11, 0.045], "dry_color": [0.3, 0.22, 0.1]}, "color_variation": 0.7, "slope": [0.0, 40.0], "avoid": 0.06,
     "responses": [respond("grazing", "density", (0.2, 0.8), (1.0, 0.25)), respond("moisture", "density", (0.6, 0.95), (1.0, 0.4)), BARE]},
    {"name": "twigs", "element": "twig", "density": 1.5, "under": 5.0, "responses": [UNDER_CANOPY]},
    {"name": "pebbles", "element": "pebble", "density": 3.0, "noise": STONY, "responses": [respond("disturbance", "density", (0.0, 0.7), (0.35, 1.0))]},
    {"name": "base_tufts", "element": "tuft", "density": 30.0, "hug": 0.35, "params": {"dry_tips": 0.3}},
    {"name": "base_pebbles", "element": "pebble", "density": 8.0, "hug": 0.3},
    {"name": "moss", "element": "tuft", "density": 120.0, "params": MOSS_PARAMS, "avoid": 0.03,
     "responses": [respond("moisture", "density", (0.4, 0.8), (0.0, 1.0)), respond("shade", "density", (0.15, 0.65), (0.1, 1.0)), respond("disturbance", "density", (0.3, 0.7), (1.0, 0.0)), respond("moisture", "height", (0.5, 1.0), (0.8, 1.4))]},
    {"name": "molehills", "element": "mound", "density": 0.012, "clumping": {"radius": 3.0, "per_clump": 6.0}, "embed": 0.1, "slope": [0.0, 25.0], "avoid": 0.3,
     "responses": [respond("soil", "density", (0.25, 0.7), (0.0, 1.0)), respond("moisture", "density", (0.75, 0.92), (1.0, 0.0)), respond("shade", "density", (0.4, 0.9), (1.0, 0.2)), respond("disturbance", "density", (0.4, 0.8), (1.0, 0.0))]},
]

FOREST_FLOOR = [
    {"name": "leaf_litter", "element": "leaf", "density": 160.0, "form": "auto", "card_distance": 6.0, "params": {"color": [0.17, 0.08, 0.03], "curl": 0.7}, "avoid": 0.02, "responses": [respond("shade", "density", (0.0, 0.5), (0.5, 1.0)), respond("disturbance", "density", (0.4, 0.9), (1.0, 0.3))]},
    {"name": "twigs", "element": "twig", "density": 6.0, "params": {"branches": 3, "length": [0.1, 0.45]}, "avoid": 0.02},
    {"name": "pebbles", "element": "pebble", "density": 2.0, "noise": STONY},
    {"name": "grass_tufts", "element": "tuft", "density": 8.0, "clumping": {"radius": 0.5, "per_clump": 6.0}, "noise": GAPS, "params": {"height": [0.08, 0.25], "color": [0.05, 0.12, 0.03], "dry_tips": 0.3}, "avoid": 0.08, "responses": [respond("shade", "density", (0.3, 0.9), (1.0, 0.2)), DRY_BY_MOISTURE]},
    {"name": "sedges", "element": "sedge", "density": 0.8, "clumping": {"radius": 0.7, "per_clump": 4.0}, "noise": PATCHES, "avoid": 0.1, "responses": [respond("moisture", "density", (0.3, 0.8), (0.2, 1.0))]},
    {"name": "base_tufts", "element": "tuft", "density": 15.0, "hug": 0.3, "params": {"color": [0.05, 0.12, 0.03]}},
    {"name": "moss", "element": "tuft", "density": 60.0, "params": MOSS_PARAMS, "avoid": 0.03, "responses": [respond("moisture", "density", (0.35, 0.75), (0.0, 1.0)), respond("shade", "density", (0.1, 0.6), (0.2, 1.0))]},
]

DRY_STEPPE = [
    {"name": "bunch_grass", "element": "grass", "density": 14.0, "clumping": {"radius": 1.2, "per_clump": 8.0}, "params": {"blades": 34, "height": [0.2, 0.5], "spread": 0.05, "lean": 25.0, "dry_tips": 0.85, "dry_length": [0.3, 0.8], "seed_heads": 0.2, "color": [0.12, 0.14, 0.05], "dry_color": [0.42, 0.34, 0.17]}, "slope": [0.0, 40.0], "avoid": 0.1,
     "responses": [TRODDEN, respond("moisture", "height", (0.0, 0.5), (0.7, 1.2)), respond("moisture", "dryness", (0.0, 0.4), (0.8, 0.2)), respond("grazing", "maturity", (0.2, 0.8), (0.8, 0.2))]},
    {"name": "dry_tufts", "element": "tuft", "density": 20.0, "noise": GAPS, "params": {"dry_tips": 0.9, "dry_length": [0.4, 0.9], "color": [0.14, 0.15, 0.06], "dry_color": [0.44, 0.36, 0.18]}, "slope": [0.0, 45.0], "avoid": 0.05, "responses": [TRODDEN]},
    {"name": "pebbles", "element": "pebble", "density": 6.0, "noise": STONY, "params": {"color": [0.36, 0.32, 0.27]}},
    {"name": "twigs", "element": "twig", "density": 0.4, "params": {"color": [0.25, 0.2, 0.14]}},
    {"name": "base_pebbles", "element": "pebble", "density": 10.0, "hug": 0.4, "params": {"color": [0.36, 0.32, 0.27]}},
    {"name": "yellow_flowers", "element": "flower", "density": 0.4, "clumping": {"radius": 0.8, "per_clump": 5.0}, "params": {"height": [0.12, 0.3], "petals": 8, "petal_length": 0.007, "petal_width": 0.004, "petal_color": [0.7, 0.5, 0.02]}, "slope": [0.0, 30.0],
     "drift": {"moisture": 3.0, "radius": [1.5, 5.0]}, "responses": [BARE]},
]

LAWN = [
    {"name": "lawn_grass", "element": "grass", "density": 300.0, "params": {"blades": 18, "height": [0.035, 0.07], "spread": 0.03, "lean": 12.0, "curvature": 0.25, "width": 0.003, "dry_tips": 0.04, "color": [0.05, 0.15, 0.025]}, "scale_range": [0.9, 1.1], "color_variation": 0.3, "slope": [0.0, 45.0], "avoid": 0.03,
     "responses": [TRODDEN, respond("moisture", "dryness", (0.05, 0.35), (0.5, 0.0)), SHADED_OUT]},
    {"name": "daisies", "element": "flower", "density": 1.0, "clumping": {"radius": 0.5, "per_clump": 8.0}, "params": {"height": [0.03, 0.06], "petals": 21, "petal_length": 0.006, "petal_width": 0.002, "centre_radius": 0.0025, "leaves": 0, "head_tilt": 10.0}, "avoid": 0.03,
     "drift": {"moisture": 5.0, "radius": [0.5, 2.0]}, "responses": [BARE]},
]

PRESET_POPULATIONS = {"meadow": MEADOW, "forest_floor": FOREST_FLOOR, "dry_steppe": DRY_STEPPE, "lawn": LAWN}
