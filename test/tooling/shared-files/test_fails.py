import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "bridge", "tests"))

from harness import run


def test_passes(bridge):
    bridge.ok("add_primitive", type="cube", name="Fine")


def test_fails_on_purpose(bridge):
    assert False, "this fixture fails on purpose"


run(globals())
