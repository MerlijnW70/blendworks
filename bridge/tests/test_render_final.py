import os
import sys
import tempfile
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import numpy as np

from final_helpers import EXACT, Recorded, camera_on_y, card, emissive, linear, noisy_wall
from harness import close, run, snapshot

from blendworks_bridge import exr_read, render_outputs
from blendworks_bridge.commands import render_final
from blendworks_bridge.registry import COMMANDS

PASS_FILES = ("depth", "normal", "albedo", "objects")


def two_objects(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0, location=[0.0, 3.0, 0.0])
    bridge.ok("add_material", name="Red", base_color=[0.8, 0.1, 0.1], roughness=0.6)
    bridge.ok("assign_material", name="Box", material="Red")
    bridge.ok("add_primitive", type="plane", name="Back", size=40.0, location=[0.0, 10.0, 0.0], rotation=[90.0, 0.0, 0.0])
    bridge.ok("add_light", type="sun", name="Sun", rotation=[60.0, 0.0, 20.0], energy=3.0)
    camera_on_y(bridge)


def render_settings():
    scene = bpy.context.scene
    cycles = scene.cycles
    return (scene.render.engine, scene.render.resolution_x, scene.render.filepath, scene.render.use_motion_blur, cycles.samples,
            cycles.time_limit, cycles.use_adaptive_sampling, cycles.seed, scene.frame_current, scene.render.image_settings.file_format,
            bpy.context.view_layer.use_pass_z, bpy.context.view_layer.use_pass_cryptomatte_object)


def test_render_final_writes_the_image_and_every_pass(bridge):
    two_objects(bridge)
    bpy.context.view_layer.update()
    before, settings = snapshot(), render_settings()
    result = bridge.ok("render_final", path="shots/hero.png", width=48, height=32, samples=16, exr=True,
                       passes=["depth", "normal", "albedo", "object_id"], device="cpu")
    assert snapshot() == before and render_settings() == settings
    assert result["files"] == {"png": "shots/hero.png", "exr": "shots/hero.exr", "passes": "shots/hero.passes.exr"}
    for name in PASS_FILES:
        assert os.path.isfile(os.path.join(bridge.workspace, "shots", f"hero.{name}.png")), name
    assert result["preview"]["mimeType"] == "image/jpeg" and result["preview"]["width"] == 48
    assert result["samples"]["cap"] == 16 and result["samples"]["rendered"] <= 16 and result["samples"]["adaptive"]
    assert result["overwritten"] == []
    assert result["denoise"]["guides"] == ["albedo", "normal"] and result["device"]["device"] == "cpu"
    assert result["deterministic"] and result["time_budget"]["stopped"] is False
    near, far = result["passes"]["depth"]["range"]
    close(near, 2.5, 0.05)
    close(far, 10.0, 0.05)
    layers = exr_read.read_exr(os.path.join(bridge.workspace, "shots", "hero.passes.exr"))
    centre = (16, 24)
    close(float(layers.channel("ViewLayer.Depth.Z")[centre]), 2.5, 0.01)
    close(float(layers.channel("ViewLayer.Depth.Z")[1, 1]), 10.0, 0.01)
    close(layers.stack("ViewLayer.Normal", "XYZ")[centre].tolist(), [0.0, -1.0, 0.0], 0.01)
    close(layers.stack("ViewLayer.Denoising Albedo", "RGB")[centre].tolist(), [0.8, 0.1, 0.1], 0.06)
    legend = result["passes"]["object_id"]["objects"]
    assert set(legend) == {"Box", "Back"}, legend
    assert legend["Box"]["color"] != legend["Back"]["color"]
    assert 0.95 * 48 * 32 <= legend["Box"]["pixels"] + legend["Back"]["pixels"] <= 48 * 32
    beauty = exr_read.read_exr(os.path.join(bridge.workspace, "shots", "hero.exr")).stack("", "RGB")
    assert beauty[centre][0] > 2.0 * beauty[centre][1]


def test_same_seed_same_image_and_another_seed_differs(bridge):
    two_objects(bridge)
    options = dict(width=40, height=30, samples=2, denoise=False, noise_threshold=0.0, time_limit=600.0, preview=False, device="cpu")
    files = []
    for name, seed in (("a", 7), ("b", 7), ("c", 8)):
        bridge.ok("render_final", path=f"{name}.png", seed=seed, **options)
        with open(os.path.join(bridge.workspace, f"{name}.png"), "rb") as handle:
            files.append(handle.read())
    assert b"tEXt" not in files[0] and b"iTXt" not in files[0] and b"zTXt" not in files[0]
    assert files[0] == files[1]
    assert files[0] != files[2]


def test_the_time_budget_stops_the_render_and_says_so(bridge):
    two_objects(bridge)
    result = bridge.ok("render_final", path="budget.png", width=96, height=96, samples=65_536, noise_threshold=0.0,
                       time_limit=0.01, denoise=False, preview=False, device="cpu")
    assert result["time_budget"]["stopped"] is True and result["time_budget"]["seconds"] == 0.01
    assert 1 <= result["samples"]["rendered"] < 65_536
    assert not result["deterministic"] and "time budget" in result["nondeterministic_because"][0]
    assert os.path.isfile(os.path.join(bridge.workspace, "budget.png"))


def test_the_budget_report_reads_samples_and_sampling_time(bridge):
    assert render_outputs.budget_report(0.0, 100, 40, 9.0, True) == {"seconds": None, "stopped": False, "sampling_seconds": 9.0}
    assert render_outputs.budget_report(10.0, 100, 40, 10.0, True)["stopped"]
    assert not render_outputs.budget_report(10.0, 100, 40, 3.0, True)["stopped"]
    assert render_outputs.budget_report(10.0, 100, 40, 3.0, False)["stopped"]
    assert not render_outputs.budget_report(10.0, 100, 100, 10.0, False)["stopped"]
    assert render_outputs.seconds_of("01:02.50") == 62.5 and render_outputs.seconds_of("1:00:00.00") == 3600.0
    assert render_outputs.seconds_of("") is None



SMALL = dict(width=64, height=64, preview=False, device="cpu", time_limit=600.0, noise_threshold=0.0)


def render_linear(bridge, name, **options):
    result = bridge.ok("render_final", path=f"{name}.exr", **dict(SMALL, **options))
    return result, linear(bridge, f"{name}.exr")


def test_denoising_removes_noise_with_openimagedenoise_guided_by_albedo_and_normal(bridge):
    noisy_wall(bridge)
    _, reference = render_linear(bridge, "reference", samples=512, denoise=False)
    with Recorded() as recorded:
        _, raw = render_linear(bridge, "raw", samples=4, denoise=False)
        result, denoised = render_linear(bridge, "denoised", samples=4, denoise=True)

    def error(image):
        return float(np.sqrt(((image - reference) ** 2).mean()))

    print(f"error against 512 samples: raw {error(raw):.4f}, denoised {error(denoised):.4f}")
    assert error(raw) > 0.01 and error(denoised) < 0.7 * error(raw)
    off, on = recorded.calls
    assert not off["denoising"] and on["denoising"] and on["layer_denoising"]
    assert (on["denoiser"], on["inputs"]) == ("OPENIMAGEDENOISE", "RGB_ALBEDO_NORMAL")
    assert result["denoise"] == {"denoiser": "openimagedenoise", "guides": ["albedo", "normal"]}


def test_a_denoised_render_is_deterministic_for_a_seed(bridge):
    noisy_wall(bridge)
    files = []
    for name, seed in (("a", 3), ("b", 3), ("c", 4)):
        result = bridge.ok("render_final", path=f"{name}.png", seed=seed, samples=4, denoise=True, **dict(SMALL, width=32, height=32))
        assert result["deterministic"] and result["nondeterministic_because"] == []
        with open(os.path.join(bridge.workspace, f"{name}.png"), "rb") as handle:
            files.append(handle.read())
    assert files[0] == files[1] and files[0] != files[2]


def test_adaptive_sampling_stops_quiet_pixels_early_and_honours_the_minimum(bridge):
    noisy_wall(bridge)
    adaptive, _ = render_linear(bridge, "adaptive", samples=64, noise_threshold=0.1, min_samples=8, denoise=False)
    fixed, _ = render_linear(bridge, "fixed", samples=64, denoise=False)
    print("samples per pixel: adaptive", adaptive["samples"]["per_pixel"], "fixed", fixed["samples"]["per_pixel"])
    assert fixed["samples"]["per_pixel"] == {"min": 64, "max": 64, "mean": 64.0}
    counts = adaptive["samples"]["per_pixel"]
    assert counts["min"] >= 8 and counts["min"] < counts["max"] <= 64 and counts["mean"] < 0.7 * 64, counts
    assert adaptive["samples"]["adaptive"] and not fixed["samples"]["adaptive"]


def test_the_time_budget_fits_inside_the_call_timeout(bridge):
    policy = COMMANDS["render_final"].policy
    margin = policy.timeout - render_final.MAX_FINAL_SECONDS
    print(f"call timeout {policy.timeout} s, longest budget {render_final.MAX_FINAL_SECONDS} s, margin {margin} s")
    assert margin == render_final.OVERHEAD_SECONDS and margin >= 2 * render_outputs.SURFACE_SECONDS + 60
    assert render_final.DEFAULT_FINAL_SECONDS <= render_final.MAX_FINAL_SECONDS and policy.max_timeout >= policy.timeout
    properties = COMMANDS["render_final"].schema["properties"]["time_limit"]
    assert properties["maximum"] == render_final.MAX_FINAL_SECONDS and properties["minimum"] > 0
    noisy_wall(bridge)
    for limit in (0.0, render_final.MAX_FINAL_SECONDS + 1.0):
        bridge.refuse("render_final", "bad_args", path="late.png", time_limit=limit)
    assert not os.path.exists(os.path.join(bridge.workspace, "late.png"))
    with Recorded() as recorded:
        bridge.ok("render_final", path="limit.png", **dict(SMALL, time_limit=render_final.MAX_FINAL_SECONDS, width=16, height=16, samples=1))
    assert recorded.calls[0]["time_limit"] == render_final.MAX_FINAL_SECONDS


def test_every_output_goes_through_the_workspace_check_and_overwrites_are_reported(bridge):
    two_objects(bridge)
    options = dict(width=16, height=16, samples=1, preview=False, device="cpu")
    outside = tempfile.mkdtemp(prefix="blendworks-outside-")
    try:
        target = os.path.join(outside, "keep.dat")
        with open(target, "wb") as handle:
            handle.write(b"keep me")
        linked = 0
        for sibling, extra in (
            ("hero.depth.png", dict(passes=["depth"])),
            ("hero.normal.png", dict(passes=["normal"])),
            ("hero.albedo.png", dict(passes=["albedo"])),
            ("hero.objects.png", dict(passes=["object_id"])),
            ("hero.passes.exr", dict(passes=["depth"])),
            ("hero.exr", dict(exr=True)),
        ):
            link = os.path.join(bridge.workspace, sibling)
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                print("symbolic links are not available here; the sibling checks are skipped")
                break
            linked += 1
            bridge.refuse("render_final", "forbidden", path="hero.png", **extra, **options)
            assert not os.path.exists(os.path.join(bridge.workspace, "hero.png"))
            with open(target, "rb") as handle:
                assert handle.read() == b"keep me", sibling
            os.remove(link)
        print(f"{linked} sibling symbolic links refused")
    finally:
        for name in os.listdir(outside):
            os.remove(os.path.join(outside, name))
        os.rmdir(outside)
    first = bridge.ok("render_final", path="again.png", passes=["depth"], **options)
    second = bridge.ok("render_final", path="again.png", passes=["depth"], **options)
    assert first["overwritten"] == []
    assert sorted(second["overwritten"]) == ["again.depth.png", "again.passes.exr", "again.png"]


def peak_bytes(work):
    tracemalloc.start()
    try:
        value = work()
        return value, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_the_exr_reader_loads_only_the_wanted_channels_and_the_header_alone(bridge):
    two_objects(bridge)
    bridge.ok("render_final", path="big.png", width=256, height=256, samples=1, passes=["depth", "normal", "albedo", "object_id"],
              denoise=False, preview=False, device="cpu")
    path = os.path.join(bridge.workspace, "big.passes.exr")
    whole, whole_peak = peak_bytes(lambda: exr_read.read_exr(path))
    depth, depth_peak = peak_bytes(lambda: exr_read.read_exr(path, lambda name: name.endswith(".Depth.Z")))
    header, header_peak = peak_bytes(lambda: exr_read.read_metadata(path))
    size = os.path.getsize(path)
    print(f"exr {size} bytes: all channels peak {whole_peak}, one channel {depth_peak}, header only {header_peak}")
    assert list(depth.channels) == ["ViewLayer.Depth.Z"] and len(whole.channels) > 10
    assert (depth.channel("ViewLayer.Depth.Z") == whole.channel("ViewLayer.Depth.Z")).all()
    assert depth_peak < 0.3 * whole_peak and header_peak < 0.1 * size
    assert header == whole.metadata


def transition_width(row):
    low, high = row.min(), row.max()
    level = (row - low) / max(high - low, 1e-9)
    return float(np.sum((level > 0.1) & (level < 0.9)))


def test_motion_blur_smears_a_moving_edge_over_the_shutter(bridge):
    card(bridge, "Mover", (-1.0, 4.0, 0.0), 2.0, 6.0, emissive(bridge, "white", 1.0))
    bridge.ok("add_camera", name="Cam", location=[0.0, 0.0, 0.0], rotation=[90.0, 0.0, 0.0], orthographic_scale=4.0)
    mover = bpy.data.objects["Mover"]
    edit = bpy.context.preferences.edit
    interpolation = edit.keyframe_new_interpolation_type
    edit.keyframe_new_interpolation_type = "LINEAR"
    try:
        for frame, x in ((1, -1.0), (3, 0.0)):
            mover.location.x = x
            mover.keyframe_insert("location", index=0, frame=frame)
    finally:
        edit.keyframe_new_interpolation_type = interpolation
    bpy.context.scene.frame_set(1)
    options = dict(width=64, height=16, samples=64, frame=2, **EXACT)
    bridge.ok("render_final", path="sharp.exr", **options)
    result = bridge.ok("render_final", path="blurred.exr", motion_blur={"shutter": 1.0}, **options)
    assert result["motion_blur"] == {"shutter": 1.0, "position": "center"} and result["frame"] == 2
    assert bpy.context.scene.frame_current == 1 and abs(mover.location.x + 1.0) < 1e-6
    sharp = transition_width(linear(bridge, "sharp.exr")[8, 24:])
    blurred = transition_width(linear(bridge, "blurred.exr")[8, 24:])
    expected = 0.5 * 64 / 4.0
    print(f"motion blur edge width: sharp {sharp} px, blurred {blurred} px, expected about {expected} px")
    assert sharp <= 2.0 and abs(blurred - expected) <= 2.0 and blurred >= 3.0 * sharp, (sharp, blurred)


def test_render_final_refuses_bad_requests(bridge):
    two_objects(bridge)
    bridge.refuse("render_final", "bad_args", path="shot.jpg")
    bridge.refuse("render_final", "forbidden", path="../outside.png")
    bridge.refuse("render_final", "bad_args", path="a.png", width=4097)
    bridge.refuse("render_final", "bad_args", path="a.png", camera="Sun")
    bridge.refuse("render_final", "not_found", path="a.png", camera="Ghost")
    bridge.refuse("render_final", "bad_args", path="a.exr", exr=True)
    bridge.refuse("render_final", "bad_args", path="a.png", samples=8, min_samples=9)
    bridge.refuse("render_final", "bad_args", path="a.png", passes=["depth", "depth"])
    bridge.refuse("render_final", "bad_args", path="a.png", depth=12)
    bpy.context.scene.camera = None
    bridge.refuse("render_final", "bad_args", path="a.png")


run(globals())
