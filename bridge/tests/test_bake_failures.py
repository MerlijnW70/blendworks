import contextlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy

from harness import run
from texture_helpers import graph_signature, world_state

from blendworks_bridge import baking, device
from blendworks_bridge.commands import bake as bake_command
from blendworks_bridge.errors import BridgeError

SIZE = 16


@contextlib.contextmanager
def patched(owner, name, replacement):
    original = getattr(owner, name)
    setattr(owner, name, replacement)
    try:
        yield original
    finally:
        setattr(owner, name, original)


@contextlib.contextmanager
def environment(value):
    saved = os.environ.get(device.ENVIRONMENT)
    os.environ[device.ENVIRONMENT] = value
    try:
        yield
    finally:
        if saved is None:
            del os.environ[device.ENVIRONMENT]
        else:
            os.environ[device.ENVIRONMENT] = saved


def textured_plane(bridge):
    bridge.ok("add_primitive", type="plane", name="Sheet", size=2.0)
    bridge.ok("material_procedural", name="Oak", wood={})
    bridge.ok("material_layer", material="Oak", dirt={"amount": 0.6}, mask="noise")
    bridge.ok("assign_material", name="Sheet", material="Oak")


def failing_on(call_number, real):
    calls = []

    def operator(*args):
        calls.append(args[1])
        if len(calls) == call_number:
            raise RuntimeError("injected bake failure")
        return real(*args)

    return operator


def test_failed_bake_leaves_material_and_images_unchanged(bridge):
    textured_plane(bridge)
    before = world_state()
    signature = graph_signature(bpy.data.materials["Oak"])
    with patched(baking, "run_bake_operator", None) as real:
        baking.run_bake_operator = failing_on(2, real)
        message = bridge.refuse("bake", "failed", names=["Sheet"], channels=["base_color", "roughness", "normal"], size=SIZE, device="cpu", rewire=True)
    assert "injected" in message and "roughness" in message
    assert graph_signature(bpy.data.materials["Oak"]) == signature
    assert world_state() == before
    assert not any(image.name.startswith("Sheet_") for image in bpy.data.images)
    assert "Sheet_baked" not in bpy.data.materials


def test_transaction_restores_the_material_when_cleanup_is_skipped(bridge):
    textured_plane(bridge)
    before = world_state()
    with patched(baking.EmissionSwap, "restore", lambda self: None):
        with patched(baking, "run_bake_operator", None) as real:
            baking.run_bake_operator = failing_on(1, real)
            bridge.refuse("bake", "failed", names=["Sheet"], channels=["metallic"], size=SIZE, device="cpu")
    assert world_state() == before
    assert not any(node.type == "EMISSION" for node in bpy.data.materials["Oak"].node_tree.nodes)


def test_failed_rewire_keeps_the_old_material(bridge):
    textured_plane(bridge)
    before = world_state()
    original = bake_command.build_pbr

    def broken(material, maps, options):
        original(material, maps, options)
        raise RuntimeError("injected rewire failure")

    with patched(bake_command, "build_pbr", broken):
        bridge.refuse("bake", "failed", names=["Sheet"], channels=["base_color", "normal"], size=SIZE, device="cpu", rewire=True)
    assert world_state() == before
    assert [slot.material.name for slot in bpy.data.objects["Sheet"].material_slots] == ["Oak"]


def test_time_limit_undoes_the_bake(bridge):
    textured_plane(bridge)
    before = world_state()

    def slow(*args):
        real(*args)
        time.sleep(1.2)

    with patched(baking, "run_bake_operator", None) as real:
        baking.run_bake_operator = slow
        message = bridge.refuse("bake", "failed", names=["Sheet"], channels=["base_color", "roughness"], size=SIZE, device="cpu", time_limit=1.0)
    assert "time limit" in message
    assert world_state() == before


def probe(backend, *names, reason=""):
    return {"backend": backend, "devices": list(names), "usable": bool(names) and not reason, "reason": reason}


NO_GPU = [probe("OPTIX", reason="no device found"), probe("CUDA", reason="not in this Blender build")]
NO_GPU_REASON = "no usable GPU (OPTIX: no device found; CUDA: not in this Blender build)"


def test_device_cpu_is_forced_by_the_environment(bridge):
    textured_plane(bridge)
    with environment("cpu"), patched(device, "probe_backends", lambda: [probe("OPTIX", "Stub GPU")]):
        result = bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=SIZE, time_limit=600.0)
    assert result["device"] == {"device": "cpu", "backend": None, "names": [], "fallback": None}
    assert result["device_label"] == "cpu"
    assert bpy.context.scene.cycles.device == "CPU"


def test_device_auto_falls_back_without_a_gpu(bridge):
    textured_plane(bridge)
    with environment("auto"), patched(device, "probe_backends", lambda: NO_GPU):
        result = bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=SIZE, time_limit=600.0)
    assert result["device"] == {"device": "cpu", "backend": None, "names": [], "fallback": NO_GPU_REASON}
    assert result["device_label"] == f"cpu (auto fell back to the CPU: {NO_GPU_REASON})"
    with patched(device, "probe_backends", lambda: []):
        assert device.choose_device("auto").fallback == "no usable GPU (no backend was probed)"
        before = world_state()
        message = bridge.refuse("bake", "failed", names=["Sheet"], channels=["base_color"], size=SIZE, device="gpu", overwrite=True)
        assert message == "BLENDWORKS_DEVICE=gpu, but no usable GPU (no backend was probed)"
        assert world_state() == before


def test_device_order_prefers_optix_then_cuda(bridge):
    order = [probe("HIP", "Radeon"), probe("CUDA", "GeForce"), probe("OPTIX", "GeForce")]
    choice = device.choose_device("auto", lambda: order)
    assert (choice.device, choice.backend, choice.label()) == ("gpu", "OPTIX", "gpu OPTIX (GeForce)")
    assert device.choose_device("gpu", lambda: order[:2]).backend == "CUDA"
    assert device.choose_device("auto", lambda: [probe("ONEAPI", "Arc"), probe("METAL", "M3")]).backend == "METAL"
    assert device.choose_device("auto", lambda: [probe("OPTIX", "GeForce", reason="broken"), probe("HIP", "Radeon")]).backend == "HIP"
    assert device.choose_device("cpu", lambda: order).device == "cpu"
    with environment(" Fast "):
        try:
            device.requested_mode()
        except BridgeError as error:
            assert error.code == "bad_args" and error.message == 'BLENDWORKS_DEVICE must be auto, gpu or cpu, not " Fast "'
        else:
            raise AssertionError("an unknown BLENDWORKS_DEVICE value was accepted")
        bridge.ok("add_primitive", type="plane", name="Sheet")
        assert "BLENDWORKS_DEVICE" in bridge.refuse("bake", "bad_args", names=["Sheet"], channels=["normal"])
    with environment(" GPU "):
        assert device.requested_mode() == "gpu"
    with environment(""):
        assert device.requested_mode() == "auto"


def test_auto_retries_on_the_cpu_when_the_gpu_bake_fails(bridge):
    textured_plane(bridge)
    with patched(device, "probe_backends", lambda: [probe("OPTIX", "Stub GPU")]), patched(device, "cycles_preferences", lambda: None):
        with patched(baking, "run_bake_operator", None) as real:
            baking.run_bake_operator = failing_on(1, real)
            result = bridge.ok("bake", names=["Sheet"], channels=["base_color"], size=SIZE, device="auto", time_limit=600.0)
    assert result["device"]["device"] == "cpu" and result["device"]["fallback"].startswith("OPTIX did not bake: ")
    assert result["images"] == ["Sheet_base_color"]


if __name__ == "__main__":
    run(globals())
