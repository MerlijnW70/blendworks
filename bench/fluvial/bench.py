import json
import os
import platform
import sys

BRIDGE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bridge"))
sys.path.insert(0, BRIDGE)

import numpy

from blendworks_bridge import fluvial_presets, fluvial_run, terrain_core

SIDE = 2048
CELL = 30.0
CASES = {
    "young_alpine": {},
    "young_alpine, base level on the south side": {"base_level": ["south"], "crest": 0.8, "behind": 0.6},
}
COLUMNS = ("seconds", "trunk_order", "hack_exponent", "hack_decades", "undrained_pits", "aspect_east_share", "aspect_north_share", "grid_bias", "local_relief", "drainage_density", "hillslope_length", "relief")


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    output = arguments[0] if arguments else os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench.json")
    terrain_core.require()
    rows = {}
    for name, overrides in CASES.items():
        settings = fluvial_presets.preset(name.split(",")[0])
        settings.update(overrides)
        result = fluvial_run.run(settings, SIDE, CELL)
        rows[name] = result["summary"]
        if name == "young_alpine":
            numpy.save(os.path.splitext(output)[0] + "_heights.npy", result["grids"]["height"])
        print(name, {key: result["summary"][key] for key in COLUMNS}, flush=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump({"side": SIDE, "cell": CELL, "cpus": os.cpu_count(), "platform": platform.platform(), "rows": rows}, handle, indent=2)


main()
