import os
import sys

assert "blendworks_bridge" not in sys.modules, "the bridge package is still imported from an earlier file"
assert "harness" not in sys.modules, "the test harness is still imported from an earlier file"
assert "BLENDWORKS_SHARED_PROBE" not in os.environ, os.environ.get("BLENDWORKS_SHARED_PROBE")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "bridge", "tests"))

import bpy

from harness import run


def test_starts_from_factory_state(bridge):
    assert "LeftBehind" not in bpy.data.objects, sorted(bpy.data.objects.keys())
    assert "LeftBehind" not in bpy.data.meshes, sorted(bpy.data.meshes.keys())
    assert bpy.context.scene.frame_current == 1, bpy.context.scene.frame_current
    import blendworks_bridge

    assert not hasattr(blendworks_bridge, "SHARED_PROBE")


run(globals())
