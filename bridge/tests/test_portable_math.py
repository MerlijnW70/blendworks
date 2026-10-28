import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy

from harness import run

from blendworks_bridge.portable_math import acos

PINNED = {
    0.5: "0x1.0c152382d7366p+0",
    -0.5: "0x1.0c152382d7366p+1",
    0.999: "0x1.6e634e566a29ep-5",
    -0.999: "0x1.8c66280ae928ep+1",
    0.3: "0x1.441f5ecbeef59p+0",
    -0.7: "0x1.2c501446cd5f2p+1",
    1e-10: "0x1.921fb543d4de0p+0",
}


def test_acos_gives_the_same_bits_on_every_platform(bridge):
    found = acos(numpy.array(list(PINNED)))
    assert [float(value).hex() for value in found] == list(PINNED.values())
    assert acos(numpy.array([1.0, -1.0, 0.0])).tolist() == [0.0, math.pi, math.pi / 2]
    assert numpy.isnan(acos(numpy.array([1.5, -1.0000001]))).all()


def test_acos_is_within_one_ulp_of_the_true_angle(bridge):
    values = numpy.concatenate([numpy.linspace(-1.0, 1.0, 400_001), numpy.random.default_rng(3).uniform(-1.0, 1.0, 200_000)])
    reference = numpy.array([math.acos(value) for value in values.tolist()])
    error = numpy.abs(acos(values) - reference) / numpy.spacing(reference)
    assert error.max() <= 1.0, error.max()


run(globals())
