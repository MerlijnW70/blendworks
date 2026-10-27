from .brass import brass, brass_schema
from .marble import DEFAULT_VEIN_COLOR, marble, vein_mask, veins_schema
from .procedural import AXES, Preset, preset_vector, stretched
from .scratches import DIRECTIONS, SCRATCH_DIRECTION_HELP, scratch_lines
from .schema import boolean, color, number, string

WAVE_FREQUENCY = 3.1831
AXIS_CHOICE = list(AXES)


def scaled(values, factor):
    return [min(1.0, value * factor) for value in values[:3]]


def spread(value, low, high):
    return max(0.0, value - low), min(1.0, value + high)


def threshold(graph, value, amount, width):
    middle = 0.7 - 0.4 * amount
    return graph.map_range(value, middle - width, middle + width)


def wood(graph, p):
    vector = preset_vector(graph, p)
    axis = p["grain"]
    rings = graph.wave(stretched(graph, vector, axis, 0.12, 1.0), p["ring_density"] / WAVE_FREQUENCY, p["ring_distortion"], 2.0, AXES[axis], kind="RINGS")
    latewood = graph.map_range(rings.outputs["Factor"], 0.62, 0.98)
    streaks = graph.noise(stretched(graph, vector, axis, 0.03, 1.0), 160.0, detail=6.0, roughness=0.6)
    fibres = graph.map_range(streaks.outputs["Factor"], 0.38, 0.62)
    patches = graph.map_range(graph.noise(stretched(graph, vector, axis, 0.25, 1.0), 4.0, detail=3.0).outputs["Factor"], 0.3, 0.7)
    figure = graph.math("MULTIPLY_ADD", latewood, 0.5, graph.math("MULTIPLY_ADD", fibres, 0.35, graph.math("MULTIPLY", patches, 0.25)), clamp=True)
    low, high = spread(p["roughness"], 0.06, 0.08)
    return {
        "base_color": graph.mix(figure, p["light_color"], p["dark_color"]),
        "roughness": graph.map_range(figure, 0.0, 1.0, low, high),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", fibres, 0.85, graph.math("MULTIPLY", latewood, 0.15)),
    }


def worn_metal(graph, p):
    vector = preset_vector(graph, p)
    wear = p["wear"]
    scratch = scratch_lines(graph, vector, p, 0.01 + 0.03 * wear)
    density = threshold(graph, graph.noise(vector, 3.0, detail=4.0, roughness=0.6).outputs["Factor"], wear, 0.1)
    scratches = graph.math("MULTIPLY", scratch, density)
    smudge = graph.noise(vector, 2.5, detail=8.0, roughness=0.6).outputs["Factor"]
    low, high = spread(p["roughness"], 0.1, 0.15)
    grime = graph.math("MULTIPLY", graph.map_range(smudge, 0.35, 0.7), 0.6 * wear)
    tarnished = graph.mix(grime, p["color"], scaled(p["color"], 0.55))
    return {
        "base_color": graph.mix(scratches, tarnished, scaled(p["color"], 1.25)),
        "roughness": graph.math("ADD", graph.map_range(smudge, 0.3, 0.7, low, high), graph.math("MULTIPLY", scratches, 0.15), clamp=True),
        "metallic": graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", grime, 0.3)),
        "height": graph.math("SUBTRACT", 1.0, scratches),
    }


def rust(graph, p):
    vector = preset_vector(graph, p)
    patches = graph.noise(vector, 3.0, detail=10.0, roughness=0.62).outputs["Factor"]
    mask = threshold(graph, patches, p["coverage"], 0.04)
    grain = graph.noise(vector, 40.0, detail=4.0, roughness=0.7).outputs["Factor"]
    flakes = graph.mix(grain, p["rust_dark"], p["rust_color"])
    return {
        "base_color": graph.mix(mask, p["metal_color"], flakes),
        "roughness": graph.mix(mask, p["metal_roughness"], graph.map_range(grain, 0.3, 0.7, 0.8, 0.95), "FLOAT"),
        "metallic": graph.math("SUBTRACT", 1.0, mask),
        "height": graph.math("MULTIPLY", mask, graph.math("MULTIPLY_ADD", grain, 0.5, 0.5)),
    }


def stone(graph, p):
    vector = preset_vector(graph, p)
    cracks = 1.0
    if p["cracks"]:
        edges = graph.voronoi(vector, p["cell_scale"], feature="DISTANCE_TO_EDGE")
        cracks = graph.map_range(edges.outputs["Distance"], 0.0, max(p["crack_width"], 0.001))
    cells = graph.voronoi(vector, p["cell_scale"])
    detail = graph.noise(vector, 14.0, detail=8.0, roughness=0.65).outputs["Factor"]
    tone = graph.mix(0.45, cells.outputs["Color"], graph.map_range(detail, 0.25, 0.75), "FLOAT")
    surface = graph.mix(graph.map_range(tone, 0.15, 0.85), p["secondary_color"], p["color"])
    low, high = spread(p["roughness"], 0.08, 0.08)
    base_color = graph.mix(graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", graph.math("SUBTRACT", 1.0, cracks), 0.75)), scaled(p["secondary_color"], 0.3), surface)
    roughness = graph.map_range(detail, 0.3, 0.7, low, high)
    height = graph.math("MULTIPLY_ADD", cracks, 0.7, graph.math("MULTIPLY", detail, 0.3))
    veins = p.get("veins")
    if veins is not None:
        mask = vein_mask(graph, vector, veins)
        base_color = graph.mix(mask, base_color, veins["color"])
        height = graph.math("MULTIPLY", height, graph.math("SUBTRACT", 1.0, graph.math("MULTIPLY", mask, 0.3)))
    return {"base_color": base_color, "roughness": roughness, "metallic": 0.0, "height": height}


def concrete(graph, p):
    vector = preset_vector(graph, p)
    stains = graph.noise(vector, 1.5, detail=6.0, roughness=0.55).outputs["Factor"]
    fine = graph.noise(vector, 60.0, detail=4.0, roughness=0.6).outputs["Factor"]
    pits = graph.voronoi(vector, 25.0, randomness=1.0)
    sparse = graph.map_range(graph.noise(vector, 9.0, detail=2.0).outputs["Factor"], 0.45, 0.6)
    pit = graph.math("MULTIPLY", graph.math("MULTIPLY", graph.map_range(pits.outputs["Distance"], 0.08, 0.16, 1.0, 0.0), sparse), p["pores"])
    tone = graph.math("MULTIPLY_ADD", graph.map_range(stains, 0.3, 0.7), 0.8, graph.math("MULTIPLY", fine, 0.2))
    surface = graph.mix(tone, scaled(p["color"], 1.0 - 0.6 * p["variation"]), scaled(p["color"], 1.0 + 0.25 * p["variation"]))
    low, high = spread(p["roughness"], 0.05, 0.05)
    return {
        "base_color": graph.mix(graph.math("MULTIPLY", pit, 0.6), surface, scaled(p["color"], 0.4)),
        "roughness": graph.map_range(fine, 0.3, 0.7, low, high),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", fine, 0.2, graph.math("SUBTRACT", 1.0, pit)),
    }


def fabric(graph, p):
    vector = preset_vector(graph, p)
    threads = p["threads"]
    warp = graph.wave(vector, threads / WAVE_FREQUENCY, 0.0, 0.0, "X").outputs["Factor"]
    weft = graph.wave(vector, threads / WAVE_FREQUENCY, 0.0, 0.0, "Y").outputs["Factor"]
    checker = graph.node("ShaderNodeTexChecker", {"Vector": vector, "Scale": threads, "Color1": (1.0, 1.0, 1.0), "Color2": (0.0, 0.0, 0.0)})
    weave = graph.mix(checker.outputs["Fac"], warp, weft, "FLOAT")
    fuzz = graph.noise(vector, threads * 0.5, detail=8.0, roughness=0.7).outputs["Factor"]
    figure = graph.math("MULTIPLY_ADD", fuzz, 0.3 * p["fuzz"], graph.math("MULTIPLY", weave, 1.0 - 0.3 * p["fuzz"]))
    low, high = spread(p["roughness"], 0.05, 0.05)
    return {
        "base_color": graph.mix(figure, p["thread_color"], p["color"]),
        "roughness": graph.map_range(figure, 0.0, 1.0, high, low),
        "metallic": 0.0,
        "height": weave,
    }


def dirt(graph, p):
    vector = preset_vector(graph, p)
    clumps = threshold(graph, graph.noise(vector, 2.0, detail=10.0, roughness=0.6).outputs["Factor"], p["amount"], 0.08)
    grain = graph.noise(vector, 30.0, detail=4.0, roughness=0.7).outputs["Factor"]
    loose = graph.mix(grain, scaled(p["color"], 0.6), p["color"])
    low, high = spread(p["roughness"], 0.05, 0.03)
    return {
        "base_color": graph.mix(clumps, loose, scaled(p["color"], 0.45)),
        "roughness": graph.map_range(grain, 0.3, 0.7, low, high),
        "metallic": 0.0,
        "height": graph.math("MULTIPLY_ADD", clumps, 0.6, graph.math("MULTIPLY", grain, 0.4)),
    }


def amount(description, default):
    return number(description, 0.0, 1.0, default)


PRESETS = {
    preset.name: preset
    for preset in (
        Preset("wood", "Wood with growth rings, fibre streaks and colour patches.", 0.2, {
            "light_color": color("Early-wood colour, linear RGB.", [0.34, 0.2, 0.095], False),
            "dark_color": color("Late-wood ring colour, linear RGB.", [0.13, 0.065, 0.03], False),
            "grain": string("Axis the grain runs along.", AXIS_CHOICE, "x"),
            "ring_density": number("Growth rings per metre.", 1.0, 500.0, 45.0),
            "ring_distortion": number("How wavy the rings are.", 0.0, 20.0, 7.0),
            "roughness": amount("Average roughness.", 0.68),
        }, wood),
        Preset("worn_metal", "Bare metal with scratches, smudges and tarnish.", 0.15, {
            "color": color("Metal colour, linear RGB.", [0.56, 0.57, 0.58], False),
            "roughness": amount("Average roughness.", 0.35),
            "wear": amount("How worn: scratch density and tarnish.", 0.4),
            "scratch_scale": number("Scratch density multiplier.", 0.1, 20.0, 1.0),
            "scratch_direction": string(SCRATCH_DIRECTION_HELP, DIRECTIONS, "x"),
        }, worn_metal),
        Preset("brass", "Aged brass: smooth polished metal with fine scratches, bright worn edges and dark patina in the recesses.", 0.05, brass_schema(), brass),
        Preset("rust", "Metal with patches of flaking rust.", 1.0, {
            "metal_color": color("Bare metal colour, linear RGB.", [0.45, 0.45, 0.47], False),
            "rust_color": color("Light rust colour, linear RGB.", [0.33, 0.11, 0.035], False),
            "rust_dark": color("Dark rust colour, linear RGB.", [0.1, 0.035, 0.012], False),
            "coverage": amount("Share of the surface covered by rust.", 0.5),
            "metal_roughness": amount("Roughness of the bare metal.", 0.4),
        }, rust),
        Preset("stone", "Stone with cells, cracks, fine grain and optional veins.", 2.0, {
            "color": color("Main stone colour, linear RGB.", [0.33, 0.31, 0.28], False),
            "secondary_color": color("Second stone colour, linear RGB.", [0.2, 0.19, 0.18], False),
            "cell_scale": number("Stone cells per metre.", 0.1, 200.0, 4.0),
            "cracks": boolean("Draw the dark cracks between the cells; false leaves a seamless stone.", True),
            "crack_width": amount("Width of the cracks between cells.", 0.05),
            "veins": veins_schema(),
            "roughness": amount("Average roughness.", 0.8),
        }, stone),
        Preset("marble", "Polished marble with warped, ridged veins and soft clouds.", 0.3, {
            "color": color("Base stone colour, linear RGB.", [0.8, 0.78, 0.73], False),
            "secondary_color": color("Cloud tint in the base, linear RGB.", [0.62, 0.6, 0.57], False),
            "vein_color": color("Vein colour, linear RGB.", DEFAULT_VEIN_COLOR, False),
            "vein_width": amount("Vein width: 0 is hair-thin, 1 is broad bands.", 0.14),
            "turbulence": amount("How far the veins wander: 0 gives straight parallel bands.", 0.5),
            "roughness": amount("Average roughness; marble is polished.", 0.18),
        }, marble),
        Preset("concrete", "Concrete with stains and small pores.", 0.5, {
            "color": color("Concrete colour, linear RGB.", [0.4, 0.39, 0.37], False),
            "variation": amount("Strength of the stains.", 0.4),
            "pores": amount("How visible the pores are.", 0.5),
            "roughness": amount("Average roughness.", 0.9),
        }, concrete),
        Preset("fabric", "Woven fabric with crossing threads and fuzz.", 0.3, {
            "color": color("Thread colour, linear RGB.", [0.22, 0.28, 0.45], False),
            "thread_color": color("Shadow colour between threads, linear RGB.", [0.08, 0.1, 0.18], False),
            "threads": number("Threads per metre (per UV unit with uv coordinates).", 1.0, 5000.0, 120.0),
            "fuzz": amount("Fuzz over the weave.", 0.3),
            "roughness": amount("Average roughness.", 0.9),
        }, fabric),
        Preset("dirt", "Dirt and dust in clumps, for overlays.", 0.4, {
            "color": color("Dirt colour, linear RGB.", [0.12, 0.09, 0.06], False),
            "amount": amount("Share of the surface with thick clumps.", 0.5),
            "roughness": amount("Average roughness.", 0.95),
        }, dirt),
    )
}
