import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy

from fingerprint import differences, fingerprint
from harness import Bridge, run

SNAPSHOT_BUDGET_SECONDS = 0.25


def allowed(bridge):
    return Bridge(bridge.workspace, allow_python=True)


def rich_scene(bridge):
    bridge.ok("add_primitive", type="cube", name="Box", size=1.0)
    bridge.ok("add_primitive", type="cylinder", name="Pipe", location=[2.0, 0.0, 0.0])
    bridge.ok("add_material", name="Paint", base_color=[0.8, 0.1, 0.1])
    bridge.ok("assign_material", name="Box", material="Paint")
    bridge.ok("add_light", type="point", name="Lamp", location=[0.0, -3.0, 3.0])
    bridge.ok("add_camera", name="Cam", location=[4.0, -4.0, 3.0], target=[0.0, 0.0, 0.0])
    bridge.ok("set_world", color=[0.1, 0.2, 0.3], strength=0.8)
    bridge.ok("curve_from_points", name="Rail", points=[[0.0, 0.0, 0.0], [1.0, 1.0, 0.0], [2.0, 0.0, 1.0]])
    bridge.ok("image_new", name="Stickers", width=8, height=8, color=[0.2, 0.4, 0.6])
    bridge.ok("image_new", name="Decal", width=8, height=8)
    bridge.ok("solidify", name="Pipe", thickness=0.05, apply=False)
    bpy.data.objects["Box"]["tag"] = "crate"
    pixels = list(bpy.data.images["Stickers"].pixels)
    pixels[0:4] = [1.0, 0.0, 1.0, 1.0]
    bpy.data.images["Stickers"].pixels[:] = pixels


DAMAGE = """
box = bpy.data.objects['Box']
bpy.data.objects.remove(bpy.data.objects['Pipe'], do_unlink=True)
paint = bpy.data.materials['Paint']
paint.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0, 1, 0, 1)
paint.node_tree.nodes.new('ShaderNodeTexNoise')
paint.diffuse_color = (0, 0, 1, 1)
bpy.data.images['Stickers'].pixels[4] = 0.0
bpy.data.images.remove(bpy.data.images['Decal'])
extra = bpy.data.collections.new('Extra')
bpy.context.scene.collection.children.link(extra)
box['tag'] = 'barrel'
box.modifiers.new('Bevel', 'BEVEL')
box.location.x = 7
box.data.vertices[0].co.z = 4
bpy.data.lights['Lamp'].energy = 9999
bpy.data.objects['Cam'].data.lens = 12
bpy.data.curves['Rail'].splines[0].points[1].co.x = 5
bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 7
bpy.data.objects.remove(bpy.data.objects['Lamp'], do_unlink=True)
raise RuntimeError('after the damage')
"""


def test_a_failing_run_python_leaves_the_scene_exactly_as_before(bridge):
    rich_scene(bridge)
    python = allowed(bridge)
    before = fingerprint()
    assert before["images"]["Stickers"]["pixels"] is not None
    message = python.refuse("run_python", "failed", code=DAMAGE)
    assert "after the damage" in message
    after = fingerprint()
    assert after == before, differences(before, after)
    assert "Pipe" in bpy.data.objects and "Decal" in bpy.data.images and "Extra" not in bpy.data.collections


def test_rollback_restores_every_kind_of_data_one_at_a_time(bridge):
    rich_scene(bridge)
    python = allowed(bridge)
    before = fingerprint()
    for line in [line for line in DAMAGE.strip().splitlines() if not line.startswith(("box =", "paint =", "raise"))]:
        code = "box = bpy.data.objects.get('Box')\npaint = bpy.data.materials.get('Paint')\n" + line + "\nraise RuntimeError('undo me')"
        python.refuse("run_python", "failed", code=code)
        after = fingerprint()
        assert after == before, (line, differences(before, after))


def test_a_successful_command_after_a_rollback_keeps_working(bridge):
    rich_scene(bridge)
    python = allowed(bridge)
    python.refuse("run_python", "failed", code=DAMAGE)
    python.ok("transform", name="Box", location=[1.0, 2.0, 3.0])
    assert list(bpy.data.objects["Box"].location) == [1.0, 2.0, 3.0]
    python.ok("delete", names=["Pipe"])
    assert "Pipe" not in bpy.data.objects


def test_the_fingerprint_sees_each_kind_of_damage(bridge):
    rich_scene(bridge)
    before = fingerprint()
    bpy.data.images["Stickers"].pixels[4] = 0.0
    assert fingerprint() != before
    bpy.data.materials["Paint"].node_tree.nodes.new("ShaderNodeTexNoise")
    changed = fingerprint()
    assert changed["materials"] != before["materials"]


def fill(count):
    collection = bpy.context.scene.collection
    template = bpy.data.meshes.new("template")
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=0.2)
    builder.to_mesh(template)
    builder.free()
    for index in range(count - len(bpy.data.meshes) + 1):
        mesh = template.copy()
        obj = bpy.data.objects.new(f"Part{index:05d}", mesh)
        obj.location = (index % 50, index // 50, 0.0)
        collection.objects.link(obj)
    bpy.data.meshes.remove(template)


def timed(bridge, cmd, rounds=7, **args):
    bridge.ok(cmd, **args)
    times = []
    for _ in range(rounds):
        started = time.perf_counter()
        bridge.ok(cmd, **args)
        times.append(time.perf_counter() - started)
    return statistics.median(times)


def test_a_no_op_mutating_command_stays_cheap_with_2000_meshes(bridge):
    fill(200)
    small = timed(bridge, "select", names=[], mode="add")
    fill(2000)
    assert len(bpy.data.meshes) >= 2000
    large = timed(bridge, "select", names=[], mode="add")
    print(f"no-op select: {small * 1000:.1f} ms with 200 meshes, {large * 1000:.1f} ms with 2000 meshes")
    assert large < SNAPSHOT_BUDGET_SECONDS, f"{large:.3f} s is over the {SNAPSHOT_BUDGET_SECONDS} s budget"
    assert large < max(small, 0.002) * 40, f"10x the meshes cost {large / max(small, 1e-9):.0f}x the time"


def test_read_only_commands_take_no_snapshot(bridge):
    bridge.ok("add_primitive", type="cube", name="Box")
    taken = bridge.handler.snapshots
    bridge.ok("scene_info")
    bridge.ok("image_info")
    bridge.ok("uv_info", name="Box")
    bridge.ok("export", path="box.glb")
    bridge.ok("checkpoint", name="ro")
    assert bridge.handler.snapshots == taken
    bridge.ok("select", names=["Box"])
    assert bridge.handler.snapshots == taken + 1


def test_read_only_commands_leave_the_scene_as_it_was(bridge):
    rich_scene(bridge)
    before = fingerprint()
    bridge.ok("scene_info", detail="full")
    bridge.ok("export", path="scene.glb")
    bridge.ok("save_blend", path="scene.blend")
    bridge.ok("checkpoint", name="look")
    bridge.ok("render_preview", views=["front"], shading="material_id", resolution=64, samples=1, device="cpu")
    bridge.ok("render_preview", focus={"object": "Box"}, shading="wireframe", resolution=64, samples=1, device="cpu")
    bridge.refuse("render_preview", "bad_args", focus={"object": "Box", "point": [0.0, 0.0, 0.0]})
    after = fingerprint()
    assert after == before, differences(before, after)


run(globals())
