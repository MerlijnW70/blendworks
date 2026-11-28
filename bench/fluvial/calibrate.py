import json
import os
import platform
import sys

TESTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bridge", "tests")
sys.path.insert(0, os.path.abspath(os.path.join(TESTS, "..")))
sys.path.insert(0, os.path.abspath(TESTS))

from fluvial_speed import CALIBRATION, measured_ratio


def main():
    ratio = round(min(measured_ratio() for _ in range(3)), 4)
    CALIBRATION.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION.write_text(json.dumps({"machine": platform.platform(), "note": "fluvial run time / calibration workload time, smallest of three", "ratio": ratio}, indent=2) + "\n", encoding="utf-8")
    print("calibrated", ratio)


main()
