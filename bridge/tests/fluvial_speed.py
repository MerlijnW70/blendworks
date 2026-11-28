import json
import time
from pathlib import Path

from blendworks_bridge import fluvial_presets, fluvial_run, fluvial_spinup
from terrain_speed import REPEATS, SLOWDOWN_FACTOR, calibration_seconds

CALIBRATION = Path(__file__).resolve().parents[2] / "bench" / "fluvial" / "speed-calibration.json"
SIDE = 257
CELL = 240.0
STEPS = 40


def workload():
    """A fixed run, the same steps whatever the surface does: no steady-state stop."""
    settings = fluvial_presets.preset("young_alpine")
    settings["threads"] = 1
    schedule = fluvial_spinup.Schedule(levels=[SIDE], steps=[STEPS], courant=[fluvial_spinup.COARSE_COURANT], tolerance=0.0)
    return fluvial_run.run(settings, SIDE, CELL, schedule)


def measured_ratio():
    workload()
    calibration = min(calibration_seconds() for _ in range(REPEATS))
    found = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        workload()
        found = min(found, time.perf_counter() - started)
    return found / calibration


def recorded_ratio():
    return json.loads(CALIBRATION.read_text(encoding="utf-8"))["ratio"]


def slowed(ratio, recorded, factor=SLOWDOWN_FACTOR):
    return ratio > factor * recorded
