import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import close, run
from kit_helpers import euler, is_closed_manifold, open_edge_count, volume

WIDTH, HEIGHT = 0.02, 0.006
RING = {"preset": "rectangle", "width": WIDTH, "height": HEIGHT}


def test_a_closed_circle_sweep_is_a_watertight_ring(bridge):
    radius = 0.1
    result = bridge.ok("sweep", name="Hoop", **RING, circle={"radius": radius}, closed=True)
    count = result["path"]["segments"]
    assert result["closed"] is True and result["manifold"] is True
    assert result["mesh"]["vertices"] == 4 * count and euler("Hoop") == 0 and open_edge_count("Hoop") == 0 and is_closed_manifold("Hoop")
    close(volume("Hoop"), WIDTH * HEIGHT * 2 * count * radius * math.sin(math.pi / count), 1e-9)


def test_a_closed_arc_sweep_joins_its_ends_with_a_chord_into_one_watertight_loop(bridge):
    radius, start, end = 0.1, 0.0, 270.0
    result = bridge.ok("sweep", name="Hook", **RING, arc={"radius": radius, "start_angle": start, "end_angle": end}, closed=True, caps=True)
    count = result["path"]["segments"]
    assert result["closed"] is True and result["manifold"] is True
    assert result["rings"] == count + 1 and result["mesh"]["vertices"] == 4 * (count + 1)
    assert euler("Hook") == 0 and open_edge_count("Hook") == 0 and is_closed_manifold("Hook")
    sweep = math.radians(end - start)
    chords = 2 * count * radius * math.sin(sweep / count / 2)
    closing = 2 * radius * math.sin((2 * math.pi - sweep) / 2)
    close(result["length"], chords + closing, 1e-6)
    close(volume("Hook"), WIDTH * HEIGHT * (chords + closing), 1e-9)


def test_an_open_arc_stays_capped_and_closed_false_on_a_circle_is_refused(bridge):
    result = bridge.ok("sweep", name="Open", **RING, arc={"radius": 0.1, "end_angle": 90.0})
    assert result["closed"] is False and result["manifold"] is True
    bridge.refuse("sweep", "bad_args", name="Hoop", **RING, circle={"radius": 0.1}, closed=False)


run(globals())
