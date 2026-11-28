import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import run

import numpy
from terrain_helpers import core_ready, grid_cases, raises, same_bits

from blendworks_bridge import terrain_core
from blendworks_bridge import terrain_kernels as kernels
from blendworks_bridge.terrain_grid import TerrainGrid


@contextlib.contextmanager
def fresh_state(**environment):
    saved_state = dict(terrain_core.STATE)
    saved_marker = dict(terrain_core.MARKER)
    saved_environment = {key: os.environ.get(key) for key in environment}
    terrain_core.STATE.clear()
    terrain_core.MARKER["path"] = Path(missing_library())
    os.environ.update(environment)
    try:
        yield
    finally:
        terrain_core.STATE.clear()
        terrain_core.STATE.update(saved_state)
        terrain_core.MARKER.update(saved_marker)
        for key, value in saved_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def missing_library():
    return os.path.join(tempfile.mkdtemp(), "absent", terrain_core.library_name())


def test_the_library_is_looked_up_where_npm_run_build_puts_it(bridge):
    expected = Path(__file__).resolve().parents[2] / "native" / "target" / "release" / terrain_core.library_name()
    assert terrain_core.default_path() == expected
    assert terrain_core.library_name("win32") == "blendworks_core.dll" and terrain_core.library_name("linux") == "libblendworks_core.so"
    assert terrain_core.configured_path({"BLENDWORKS_NATIVE_LIB": "/x/core.so"}) == Path("/x/core.so")


def test_a_missing_core_falls_back_to_the_python_reference_with_one_stated_reason(bridge):
    missing = missing_library()
    errors = io.StringIO()
    heights, spacing, edges = grid_cases()["pits"]
    with fresh_state(BLENDWORKS_NATIVE_LIB=missing, BLENDWORKS_NATIVE="off"), contextlib.redirect_stderr(errors):
        assert terrain_core.core() is None and terrain_core.core() is None
        receivers, _ = kernels.d8(heights, spacing, edges)
        filled, _ = kernels.priority_flood(heights, True, edges)
        status = terrain_core.status()
    lines = [line for line in errors.getvalue().splitlines() if line.startswith("blendworks:")]
    assert len(lines) == 1, errors.getvalue()
    assert missing in lines[0] and "Python reference" in lines[0] and "npm run build" in lines[0]
    assert status["loaded"] is False and missing in status["reason"]
    same_bits(receivers, kernels.d8(heights, spacing, edges, engine="python")[0])
    same_bits(filled, kernels.priority_flood(heights, True, edges, engine="python")[0])


def test_a_file_that_is_not_a_library_is_reported_with_its_cause(bridge):
    broken = Path(tempfile.mkdtemp()) / terrain_core.library_name()
    broken.write_bytes(b"this is not a shared library")
    found, reason = terrain_core.load(broken)
    assert found is None and str(broken) in reason and "failed to load" in reason


def test_where_the_core_is_required_a_missing_core_is_an_error_not_a_fallback(bridge):
    heights = numpy.arange(12.0).reshape(3, 4)
    with fresh_state(BLENDWORKS_NATIVE_LIB=missing_library(), BLENDWORKS_NATIVE="require"), contextlib.redirect_stderr(io.StringIO()):
        assert terrain_core.required()
        error = raises(kernels.d8, heights)
        assert isinstance(error, terrain_core.CoreMissing) and "required" in str(error)
        kernels.d8(heights, engine="python")
    with fresh_state(BLENDWORKS_NATIVE_LIB=missing_library(), BLENDWORKS_NATIVE="off"), contextlib.redirect_stderr(io.StringIO()):
        assert not terrain_core.required()
        assert isinstance(raises(kernels.d8, heights, engine="core"), terrain_core.CoreMissing)
    assert terrain_core.required({"BLENDWORKS_NATIVE": "require"}, Path(missing_library()))
    assert not terrain_core.required({}, Path(missing_library()))


def test_the_image_marker_makes_the_core_mandatory_and_it_loads(bridge):
    if terrain_core.REQUIRED_MARKER.is_file():
        assert terrain_core.required()
        assert terrain_core.core() is not None, f"the judge image requires the native core: {terrain_core.STATE.get('reason')}"
    else:
        print(f"skip: {terrain_core.REQUIRED_MARKER} exists only in the judge image")
    assert kernels.chosen_core("python") is None
    assert isinstance(raises(kernels.chosen_core, "fast"), ValueError)


def test_the_core_reads_and_writes_the_callers_numpy_buffers_in_place(bridge):
    if not core_ready():
        return
    found = terrain_core.core()
    heights = numpy.ascontiguousarray(grid_cases()["random"][0])
    grid = TerrainGrid.of(heights)
    receivers = numpy.full(grid.count, -7, dtype=numpy.int32)
    described = terrain_core.describe(receivers)
    assert described.data == receivers.ctypes.data and described.len == receivers.size
    found.call("bw_d8", terrain_core.grid_spec(grid), 2, terrain_core.describe(heights), described, terrain_core.I64(0))
    same_bits(receivers, kernels.d8(heights, engine="python")[0])
    strided = numpy.zeros(grid.count * 2, dtype=numpy.int32)[::2]
    error = raises(found.call, "bw_d8", terrain_core.grid_spec(grid), 2, terrain_core.describe(heights), terrain_core.describe(strided), terrain_core.I64(0))
    assert "C-contiguous" in str(error) and not strided.any()


run(globals())
