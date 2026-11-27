import cProfile
import io
import json
import math
import os
import pstats
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))
sys.path.insert(0, HERE)

import bpy
import numpy

import measures
from blendworks_bridge import Handler

SIZES = {
    "full": {
        "land_resolution": 301, "rings": ((300.0, range(3, 6), 101, 4.0), (900.0, range(0, 3), 91, 10.0), (2700.0, range(-1, 2), 55, 40.0)),
        "trees": 30, "full_detail": 3, "budget": 1_500_000, "near": 120.0, "rocks": 900, "river_trials": 3,
        "width": 1920, "height": 1080, "samples": 4, "time_limit": 600.0,
    },
    "check": {
        "land_resolution": 121, "rings": ((300.0, range(3, 6), 21, 4.0),),
        "trees": 3, "full_detail": 0, "budget": 20_000, "near": 40.0, "rocks": 120, "river_trials": 1,
        "width": 96, "height": 54, "samples": 4, "time_limit": 120.0,
    },
}
SPECIES = ("oak", "birch", "pine")
TILE = 300.0
SHIFT = 4.5 * TILE
SEED = 3
ROLLING = {"height": 9.0, "scale": 180.0, "octaves": 5, "hurst": 0.8}
HILLS = {"amplitude": 100.0, "seed": 260, "scale": 2500.0, "octaves": 3, "hurst": 0.5}
TIMED = ("scatter", "ground_cover", "grow_tree", "tree_mesh", "tree_leaves", "liquid_body", "material_layer", "weather",
         "atmosphere", "render_final")


class Bench:
    def __init__(self, out, size, profile):
        self.out = out
        self.size = SIZES[size]
        self.handler = Handler(out, allow_python=False, desktop=False)
        self.calls = []
        self.profile = profile
        self.profiles = {}
        self.autosave_cpu = 0.0
        saving = self.handler.autosave.save

        def timed_save(reason):
            started = time.process_time()
            try:
                return saving(reason)
            finally:
                self.autosave_cpu += time.process_time() - started

        self.handler.autosave.save = timed_save

    def cmd(self, name, /, **args):
        return self.call(name, True, args)

    def attempt(self, name, /, **args):
        return self.call(name, False, args)

    def call(self, name, required, args):
        profiler = cProfile.Profile() if self.profile and name in TIMED else None
        wall = time.perf_counter()
        cpu = time.process_time()
        saved = self.autosave_cpu
        if profiler:
            profiler.enable()
        reply = self.handler.handle({"cmd": name, "args": args})
        if profiler:
            profiler.disable()
        spent_cpu = time.process_time() - cpu
        spent_wall = time.perf_counter() - wall
        autosave = self.autosave_cpu - saved
        spent_cpu -= autosave
        self.calls.append({"cmd": name, "ok": reply["ok"], "cpu": round(spent_cpu, 3), "autosave": round(autosave, 3), "wall": round(spent_wall, 3),
                           "peak_memory": measures.peak_memory_bytes()})
        if profiler:
            if name in self.profiles:
                self.profiles[name].add(profiler)
            else:
                self.profiles[name] = pstats.Stats(profiler)
        if not reply["ok"]:
            if required:
                raise RuntimeError(f"{name}: {reply['error']['message']}")
            return None
        print(f"ok {name} cpu {spent_cpu:.2f} wall {spent_wall:.2f}", flush=True)
        return reply["result"]


def slow_down(setting):
    """BLENDWORKS_BENCH_SLOW=module.function=seconds makes one bridge function burn that much more CPU per call, so a test
    can show that the speed guard catches a slower tool."""
    import importlib

    target, seconds = setting.rsplit("=", 1)
    module_name, function_name = target.rsplit(".", 1)
    module = importlib.import_module(f"blendworks_bridge.{module_name}")
    original = getattr(module, function_name)

    def slowed(*args, **kwargs):
        started = time.process_time()
        while time.process_time() - started < float(seconds):
            sum(range(1000))
        return original(*args, **kwargs)

    setattr(module, function_name, slowed)


def tile(bench, name, size, index, resolution, skirt):
    extra = {"skirt": True, "skirt_depth": skirt} if skirt else {}
    bench.cmd("heightfield", name=name, size=[size, size], tile=list(index), resolution=resolution, seed=SEED, **ROLLING, **extra)
    bench.cmd("transform", name=name, location=[index[0] * size - SHIFT, index[1] * size - SHIFT, 0.0])
    bench.cmd("noise_displace", name=name, direction="z", **HILLS)
    bench.cmd("assign_material", name=name, material="ground")


def terrain(bench):
    bench.cmd("material_procedural", name="ground", grass_ground={"density": 0.75, "dryness": 0.2})
    tile(bench, "land", TILE, (4, 4), bench.size["land_resolution"], None)
    for size, indices, resolution, skirt in bench.size["rings"]:
        centre = (indices.start + indices.stop - 1) // 2
        for i in indices:
            for j in indices:
                if (i, j) != (centre, centre):
                    tile(bench, f"ground_{int(size)}_{i}_{j}", size, (i, j), resolution, skirt)


def land_points():
    obj = bpy.data.objects["land"]
    local = numpy.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", local)
    matrix = numpy.array(obj.matrix_world)
    return local.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]


def lake(bench, heights):
    inner = heights[(numpy.abs(heights[:, 0]) < TILE * 0.3) & (numpy.abs(heights[:, 1]) < TILE * 0.3)]
    lowest = inner[numpy.argmin(inner[:, 2])]
    report = bench.cmd("liquid_body", kind="lake", name="lake", ground=["land"], point=[float(lowest[0]), float(lowest[1]), 0.0], seed=3)
    water = heights[numpy.abs(heights[:, 2] - report["level"]) < 0.5]
    report["centre"] = [float(numpy.median(water[:, 0])), float(numpy.median(water[:, 1]))]
    return report


def river(bench, heights, report):
    level = report["level"]
    centre = numpy.array(report["centre"])
    ring = heights[(heights[:, 2] > level + 2.0) & (numpy.abs(heights[:, 0]) < TILE * 0.45) & (numpy.abs(heights[:, 1]) < TILE * 0.45)]
    reach = numpy.hypot(ring[:, 0] - centre[0], ring[:, 1] - centre[1])
    ring, reach = ring[reach > 45.0], reach[reach > 45.0]
    found = []
    for index in numpy.argsort(-reach, kind="stable")[: 8000: 40]:
        source = [float(ring[index][0]), float(ring[index][1]), 0.0]
        trial = bench.attempt("liquid_body", kind="river", name="river", ground=["land"], point=source, width=4.0, depth=0.6, carve=False, wet_shore=False)
        if trial is None:
            continue
        bench.cmd("delete", names=["river"])
        if trial["joins"] == "water" and trial["length"] > 80.0:
            found.append((trial["mean_speed"], source))
            if len(found) == bench.size["river_trials"]:
                break
    if not found:
        raise RuntimeError("no river source drains into the lake")
    _, source = min(found)
    return bench.cmd("liquid_body", kind="river", name="river", ground=["land"], point=source, width=4.0, depth=0.6, seed=5)


def rocks(bench):
    bench.cmd("material_procedural", name="rock", stone={"color": [0.2, 0.19, 0.175], "secondary_color": [0.1, 0.095, 0.088], "cell_scale": 2.5, "cracks": False, "roughness": 0.8})
    bench.cmd("material_layer", material="rock", mask="up_facing", moss={}, amount=0.2, softness=0.5, seed=4)
    variants = []
    for index, size in enumerate(([1.0, 0.8, 0.6], [1.2, 0.75, 0.55], [0.8, 0.7, 0.65], [1.1, 0.9, 0.5])):
        name = f"rock_{index}"
        bench.cmd("add_primitive", type="ico_sphere", name=name, radius=0.5, subdivisions=1, location=[0.0, 0.0, 0.5 * size[2]], rotation=[0.0, 0.0, 17.0 * index])
        bench.cmd("transform", name=name, scale=size)
        bench.cmd("apply_transform", name=name, location=True, rotation=True, scale=True)
        bench.cmd("chip", name=name, count=6, depth=0.12, seed=31 + index)
        bench.cmd("abrade", name=name, amount=0.7, seed=index, edge_length=0.04)
        bench.cmd("noise_displace", name=name, amplitude=0.04, seed=7 + index, scale=0.5, octaves=4, hurst=0.6)
        bench.cmd("shade_smooth", name=name)
        bench.cmd("uv_smart_project", name=name)
        bench.cmd("assign_material", name=name, material="rock")
        variants.append(name)
    placed = bench.cmd("scatter", target="land", sources=[{"name": name, "weight": 1.0} for name in variants], min_distance=0.6,
                       density_mask=["shore", "noise"], shore_width=2.5, shore_depth=0.3, shore_wet=0.6,
                       noise={"scale": 18.0, "octaves": 2, "threshold": 0.3, "softness": 0.25, "seed": 9},
                       scale_range=[0.3, 2.2], scale_distribution="power", scale_exponent=-2.2, embed=0.25, align="blend", align_factor=0.3,
                       seed=4, name="shore_rocks", realize=True, max_count=bench.size["rocks"])
    bench.cmd("delete", names=variants)
    return placed


def trees(bench, heights, level, mouth):
    generator = numpy.random.default_rng(6)
    near = numpy.hypot(heights[:, 0] - mouth[0], heights[:, 1] - mouth[1])
    dry = heights[(heights[:, 2] > level + 1.5) & (near > 12.0) & (near < 110.0)]
    chosen = []
    for spot in dry[generator.permutation(len(dry))]:
        if all(math.hypot(spot[0] - other[0], spot[1] - other[1]) > 9.0 for other in chosen):
            chosen.append(spot)
        if len(chosen) == bench.size["trees"]:
            break
    planted = []
    for index, spot in enumerate(chosen):
        name = f"tree_{index}"
        bench.cmd("grow_tree", name=name, preset=SPECIES[index % len(SPECIES)], seed=10 + index, location=[float(spot[0]), float(spot[1]), float(spot[2]) - 0.1], limit=0)
        bench.cmd("tree_mesh", name=name)
        bench.cmd("tree_leaves", name=f"{name}_bark", leaves_name=f"{name}_leaves", seed=10 + index, detail="full" if index < bench.size["full_detail"] else "low")
        planted.append(f"{name}_bark")
    return planted


def ground_at(heights, x, y):
    return float(heights[numpy.argmin(numpy.hypot(heights[:, 0] - x, heights[:, 1] - y)), 2])


def cameras(bench, heights, report, mouth):
    level = report["level"]
    centre = numpy.array(report["centre"])
    best = None
    for distance in (90.0, 110.0, 130.0, 150.0, 170.0):
        for angle in numpy.radians(numpy.arange(0.0, 360.0, 5.0)):
            spot = mouth[:2] + distance * numpy.array([math.cos(angle), math.sin(angle)])
            if numpy.abs(spot).max() > TILE / 2.0 - 25.0 or ground_at(heights, *spot) < level + 2.0:
                continue
            ahead = (mouth[:2] - spot) / distance
            miss = abs(float(ahead[0] * (centre[1] - spot[1]) - ahead[1] * (centre[0] - spot[0])))
            if best is None or miss < best[0]:
                best = (miss, spot)
    spot = best[1]
    target = [float(0.5 * (mouth[0] + centre[0])), float(0.5 * (mouth[1] + centre[1])), level]
    bench.cmd("add_camera", name="eye", location=[float(spot[0]), float(spot[1]), ground_at(heights, *spot) + 12.0], target=target, lens=26.0)
    bench.cmd("camera_setup", name="eye", view_transform="AgX", look="base_contrast")
    side = mouth[:2] + 0.35 * (centre - mouth[:2])
    stand = side + numpy.array([-(centre - mouth[:2])[1], (centre - mouth[:2])[0]]) * 0.25
    bench.cmd("add_camera", name="shore", location=[float(stand[0]), float(stand[1]), ground_at(heights, *stand) + 1.7],
              target=[float(side[0]), float(side[1]), level + 0.5], lens=32.0)
    bench.cmd("camera_setup", name="shore", view_transform="AgX", look="base_contrast")
    return ["eye", "shore"]


def build(bench):
    bench.cmd("new_scene")
    terrain(bench)
    bench.cmd("weather", preset="fair_cumulus", time_of_day="afternoon", form="auto", seed=2, haze=False)
    heights = land_points()
    report = lake(bench, heights)
    flow = river(bench, heights, report)
    mouth = numpy.array(flow["path"][-1])
    heights = land_points()
    placed = rocks(bench)
    planted = trees(bench, heights, report["level"], mouth)
    shots = cameras(bench, heights, report, mouth)
    obstacles = placed.get("objects") or [placed["name"]]
    reeds = [{"name": "reeds", "element": "sedge", "density": 25.0, "liquid": "shore", "shore": 1.2, "clumping": {"radius": 0.6, "per_clump": 12.0}}]
    bench.cmd("ground_cover", target="land", preset="meadow", cameras=shots, near=bench.size["near"], view_only=True, budget=bench.size["budget"],
              obstacles=obstacles + planted, trees=planted, seed=5, populations=reeds)
    bench.cmd("atmosphere", visibility=10000.0, height_falloff=300.0)


def profile_tables(bench, rows=25):
    tables = {}
    for name, stats in bench.profiles.items():
        stream = io.StringIO()
        stats.stream = stream
        stats.sort_stats("cumulative").print_stats(rows)
        tables[name] = stream.getvalue()
    return tables


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(arguments[0] if arguments else os.path.join(os.getcwd(), "scene-speed"))
    size = arguments[1] if len(arguments) > 1 else "check"
    profile = "profile" in arguments[2:]
    os.makedirs(out, exist_ok=True)
    calibration = measures.calibration_seconds()
    if os.environ.get("BLENDWORKS_BENCH_SLOW"):
        slow_down(os.environ["BLENDWORKS_BENCH_SLOW"])
    bench = Bench(out, size, profile)
    build(bench)
    measured = measures.geometry(bpy.context.scene)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "scene.blend"), compress=False)
    summary = {"size": size, "environment": measures.environment(), "calibration": round(calibration, 4), "geometry": measured}
    write(out, bench, summary)
    if "build" in arguments[2:]:
        return
    settings = bench.size
    final = bench.cmd("render_final", path="scene.png", camera="eye", width=settings["width"], height=settings["height"],
                      samples=settings["samples"], time_limit=settings["time_limit"], device="cpu", preview=False)
    summary["image"] = measures.image_statistics(os.path.join(out, "scene.png"))
    summary["render"] = {key: final.get(key) for key in ("samples", "seconds", "determinism")}
    write(out, bench, summary)


def write(out, bench, summary):
    per_tool = {}
    for call in bench.calls:
        entry = per_tool.setdefault(call["cmd"], {"calls": 0, "cpu": 0.0, "wall": 0.0})
        entry["calls"] += 1
        entry["cpu"] = round(entry["cpu"] + call["cpu"], 3)
        entry["wall"] = round(entry["wall"] + call["wall"], 3)
    summary["total"] = {"cpu": round(sum(call["cpu"] for call in bench.calls), 3), "wall": round(sum(call["wall"] for call in bench.calls), 3),
                        "autosave": round(sum(call["autosave"] for call in bench.calls), 3)}
    summary["peak_memory"] = measures.peak_memory_bytes()
    summary["tools"] = per_tool
    summary["calls"] = bench.calls
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1, default=str)
    for name, table in profile_tables(bench).items():
        with open(os.path.join(out, f"profile-{name}.txt"), "w", encoding="utf-8") as handle:
            handle.write(table)


if __name__ == "__main__":
    main()
