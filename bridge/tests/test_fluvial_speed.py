BLENDWORKS_FRESH_PROCESS = "times a fluvial run against a calibration workload, which files before it in a shared process would disturb"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

from fluvial_speed import SLOWDOWN_FACTOR, measured_ratio, recorded_ratio, slowed
from terrain_helpers import core_ready


def test_the_guard_flags_only_ratios_beyond_the_stated_factor(bridge):
    assert not slowed(SLOWDOWN_FACTOR * 0.99, 1.0)
    assert slowed(SLOWDOWN_FACTOR * 1.01, 1.0)


def test_a_fluvial_run_is_not_slower_than_its_calibrated_time_by_the_stated_factor(bridge):
    if not core_ready():
        return
    ratio, recorded = measured_ratio(), recorded_ratio()
    print("fluvial run against calibration:", round(ratio / recorded, 2))
    assert not slowed(ratio, recorded), f"the fluvial run took {ratio / recorded:.2f} times its calibrated time, past {SLOWDOWN_FACTOR}"


run(globals())
