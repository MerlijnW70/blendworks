import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "bridge", "tests"))

import bpy

from harness import run


def test_changes_what_the_reset_restores(bridge):
    bridge.ok("add_primitive", type="cube", name="LeftBehind")
    bpy.context.scene.frame_current = 42
    os.environ["BLENDWORKS_SHARED_PROBE"] = "set by test_clean_a"
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    import blendworks_bridge

    blendworks_bridge.SHARED_PROBE = "set by test_clean_a"


run(globals())
