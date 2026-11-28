BLENDWORKS_FRESH_PROCESS = "times kernels against a calibration workload, which files before it in a shared process would disturb"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from terrain_helpers import core_ready
from terrain_speed import SLOWDOWN_FACTOR, measured_ratios, recorded_ratios, slowed


def test_the_guard_flags_only_ratios_beyond_the_stated_factor(bridge):
    recorded = {"fast": 1.0, "slow": 2.0}
    assert slowed({"fast": SLOWDOWN_FACTOR * 0.99, "slow": 2.0}, recorded) == {}
    found = slowed({"fast": SLOWDOWN_FACTOR * 1.5, "slow": 2.0}, recorded)
    assert list(found) == ["fast"] and abs(found["fast"] - SLOWDOWN_FACTOR * 1.5) < 1e-12


def test_no_kernel_is_slower_than_its_calibrated_time_by_the_stated_factor(bridge):
    if not core_ready():
        return
    recorded = recorded_ratios()
    ratios = measured_ratios()
    assert set(ratios) == set(recorded), sorted(set(ratios) ^ set(recorded))
    print("speed ratios against calibration:", {name: round(ratios[name] / recorded[name], 2) for name in ratios})
    assert slowed(ratios, recorded) == {}, f"kernels slower than {SLOWDOWN_FACTOR} x their calibrated time: {slowed(ratios, recorded)}"


def test_the_guard_catches_a_kernel_slowed_to_the_python_reference(bridge):
    if not core_ready():
        return
    recorded = recorded_ratios()
    ratios = measured_ratios({"accumulation": "python", "lake routing": "python"})
    found = slowed(ratios, recorded)
    assert set(found) == {"accumulation", "lake routing"}, f"slowed kernels found: {found}"


run(globals())
