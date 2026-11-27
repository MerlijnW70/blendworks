"""The "to the horizon" option of the example scenes: distant land around the scene's terrain, forest on it, mist in the
low ground and haze over everything. Each example calls surround() after it has built its own land and cameras; with
the option off it is never called and the scene renders as before."""
import os

OPTION = os.environ.get("BLENDWORKS_HORIZON", "")
FOREST_DETAIL = float(os.environ.get("BLENDWORKS_HORIZON_TREES", "0.3"))
LAND_DETAIL = int(os.environ.get("BLENDWORKS_HORIZON_DETAIL", "128"))
FRAMES = int(os.environ.get("BLENDWORKS_HORIZON_FRAMES", "8"))


def enabled():
    return OPTION in ("rolling", "ranges")


def surround(cmd, terrain, camera, water=(), species=("pine", "oak", "birch"), visibility=25_000.0, mist=None, forest=True, cover=0.45, seed=0, haze=True):
    """Land, forest, mist and haze to the horizon around terrain, built for camera."""
    land = cmd("distant_land", terrain=list(terrain), style=OPTION, camera=camera, detail=LAND_DETAIL, seed=seed)
    report = {"land": {key: land[key] for key in ("triangles", "rings", "border", "statistics", "curvature")}}
    if forest:
        grown = cmd("distant_forest", land=land["name"], camera=camera, species=list(species), tree_detail=FOREST_DETAIL,
                    frames=FRAMES, cover=cover, seed=seed)
        report["forest"] = {key: grown[key] for key in ("counts", "cover", "switches", "calibration")}
    if mist is not None:
        made = cmd("valley_mist", ground=list(terrain) + [land["name"]] + list(water), **mist)
        report["mist"] = {key: made[key] for key in ("coverage", "low_ground", "extinction_per_metre")}
    if haze:
        made = cmd("atmosphere", visibility=visibility, height_falloff=1200.0, method="depth")
        report["haze"] = {"visibility": made["visibility"], "method": made["method"]}
    return report
