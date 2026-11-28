import json
import os
import platform
import sys

TESTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bridge", "tests")
sys.path.insert(0, os.path.abspath(os.path.join(TESTS, "..")))
sys.path.insert(0, os.path.abspath(TESTS))

from terrain_speed import CALIBRATION, measured_ratios


def main():
    runs = [measured_ratios() for _ in range(3)]
    ratios = {name: round(min(run[name] for run in runs), 4) for name in runs[0]}
    CALIBRATION.write_text(json.dumps({"machine": platform.platform(), "note": "kernel time / calibration workload time, smallest of three runs", "ratios": ratios}, indent=2) + "\n", encoding="utf-8")
    print("calibrated", ratios)


main()
