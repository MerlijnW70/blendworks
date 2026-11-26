import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from harness import close, run
from sky_helpers import angle_between, fisheye_directions, fisheye_up, lamp_direction, luminance, render

from blendworks_bridge import sky_sun

FISHEYE = 128
DIRECTION_TOLERANCE = 2.5


def test_lamp_points_at_the_brightest_point_of_the_sky(bridge):
    camera = fisheye_up(bridge)
    directions, zenith, inside = fisheye_directions(FISHEYE)
    for elevation, azimuth in ((60.0, 135.0), (25.0, 300.0), (8.0, 20.0)):
        result = bridge.ok("sky", sun={"elevation": elevation, "azimuth": azimuth}, sun_size=4.0, exposure="keep")
        pixels = luminance(render(bridge, f"sky_{int(elevation)}", FISHEYE, 2, camera))
        pixels[~inside] = 0.0
        row, column = np.unravel_index(np.argmax(pixels), pixels.shape)
        brightest = directions[row, column]
        assert angle_between(brightest, lamp_direction()) <= DIRECTION_TOLERANCE, (elevation, azimuth, brightest)
        close(result["sun"]["direction"], list(sky_sun.direction(elevation, azimuth)), 1e-5)


def test_sun_reddens_and_dims_towards_the_horizon(bridge):
    lamps = []
    for elevation in (60.0, 20.0, 5.0, 1.0):
        lamps.append(bridge.ok("sky", sun={"elevation": elevation, "azimuth": 180.0}, exposure="keep")["lamp"])
    strengths = [lamp["strength"] for lamp in lamps]
    blues = [lamp["color"][2] / lamp["color"][0] for lamp in lamps]
    assert all(a > b for a, b in zip(strengths, strengths[1:])), strengths
    assert all(a > b for a, b in zip(blues, blues[1:])), blues
    assert lamps[0]["color"][2] > 0.5 and lamps[-1]["color"][2] < 0.05
    below = bridge.ok("sky", sun={"elevation": -4.0, "azimuth": 180.0}, exposure="keep")
    assert below["lamp"]["strength"] == 0.0 and below["sun"]["below_horizon"]
    assert below["sky"]["illuminance"] > 0.0


def test_sun_from_date_time_and_place(bridge):
    result = bridge.ok("sky", sun={"date": "2024-06-20", "time": "12:00", "latitude": 51.4769, "longitude": 0.0, "utc_offset": 0.0}, exposure="keep")
    close(result["sun"]["elevation"], 90.0 - 51.4769 + 23.438, 0.05)
    assert 178.0 < result["sun"]["azimuth"] < 180.5
    morning = bridge.ok("sky", sun={"date": "2024-03-20", "time": "06:07", "latitude": 0.0, "longitude": 0.0, "utc_offset": 0.0}, exposure="keep")
    close(morning["sun"]["azimuth"], 90.0, 0.5)
    close(morning["sun"]["elevation"], 0.0, 1.0)
    bridge.refuse("sky", "bad_args", sun={"date": "2024-02-30", "time": "12:00", "latitude": 0.0, "longitude": 0.0})
    bridge.refuse("sky", "bad_args", sun={"elevation": 30.0, "date": "2024-02-03"})


def test_strength_scales_lamp_and_sky_together(bridge):
    one = bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 0.0}, exposure="keep")
    two = bridge.ok("sky", sun={"elevation": 40.0, "azimuth": 0.0}, strength=2.0, exposure="keep")
    close(two["lamp"]["strength"], 2.0 * one["lamp"]["strength"], 1e-3)
    close(two["sky"]["horizontal_irradiance"], [2.0 * value for value in one["sky"]["horizontal_irradiance"]], 1e-3)
    assert one["lamp"]["created"] and not two["lamp"]["created"]
    assert sum(1 for obj in bpy.context.scene.objects if obj.type == "LIGHT") == 1


def test_auto_exposure_opens_up_for_low_light(bridge):
    noon = bridge.ok("sky", sun={"elevation": 60.0, "azimuth": 180.0})
    dusk = bridge.ok("sky", sun={"elevation": -3.0, "azimuth": 180.0})
    assert abs(noon["exposure"]["scene"]) < 0.5
    assert dusk["exposure"]["scene"] > noon["exposure"]["scene"] + 3.0
    close(bpy.context.scene.view_settings.exposure, dusk["exposure"]["recommended"], 1e-4)
    kept = bridge.ok("sky", sun={"elevation": 60.0, "azimuth": 180.0}, exposure="keep")
    close(kept["exposure"]["scene"], dusk["exposure"]["recommended"], 1e-4)


def test_sky_refuses_a_lamp_that_is_not_a_sun(bridge):
    bridge.ok("add_light", type="point", name="Bulb")
    bridge.refuse("sky", "bad_args", lamp="Bulb")
    bridge.refuse("sky", "bad_args", sun={"elevation": -30.0})


run(globals())
