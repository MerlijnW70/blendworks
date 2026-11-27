import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import numpy
from mathutils import Matrix, Vector

from harness import run

from blendworks_bridge import exr_read, floating_origin, floating_shaders, limits

FAR = 150_000.0
DETAIL = 0.001
SIZE = 64
CONTRAST = 0.2
CHANGED = 0.05
EDGE_PIXELS = SIZE * SIZE // 100
LUMINANCE = numpy.array([0.2126, 0.7152, 0.0722])
CLOUD_MATCH = 0.02
SHIFT_FOR = floating_origin.shift_for


def world_float32(obj):
    """Vertex positions in world space as the renderer stores them: float32."""
    local = numpy.array([vertex.co for vertex in obj.data.vertices], dtype=numpy.float64)
    matrix = numpy.array(obj.matrix_world, dtype=numpy.float64)
    world = local @ matrix[:3, :3].T + matrix[:3, 3]
    return world.astype(numpy.float32).astype(numpy.float64), local


def shape_error(obj):
    world, local = world_float32(obj)
    return float(numpy.abs((world - world[0]) - (local - local[0])).max())


def fine_mesh(bridge, location):
    steps = [[i * DETAIL, (i % 3) * DETAIL, (i % 2) * DETAIL] for i in range(30)]
    bridge.ok("mesh_from_data", name="fine", vertices=steps, faces=[[i, i + 1, i + 2] for i in range(28)])
    bridge.ok("transform", name="fine", location=location)


def far_scene(bridge):
    fine_mesh(bridge, [FAR + 0.3217, -FAR + 0.6061, 12.5])
    bridge.ok("add_camera", name="eye", location=[FAR, -FAR + 0.5, 13.0], target=[FAR + 0.3, -FAR + 0.6, 12.5])
    bridge.ok("add_light", type="sun", name="sun")


def unshifted(point):
    return None


class Unshifted:
    """The control: the same render with the world left where it is."""

    def __enter__(self):
        floating_origin.shift_for = unshifted

    def __exit__(self, *rest):
        floating_origin.shift_for = SHIFT_FOR


def test_rendering_far_out_keeps_millimetre_detail_in_world_space(bridge):
    far_scene(bridge)
    fine = bpy.data.objects["fine"]
    scene = bpy.context.scene
    scene.camera = bpy.data.objects["eye"]
    assert shape_error(fine) > 2 * DETAIL, "float32 world space at 150 km should lose millimetres"
    with floating_origin.camera_relative(scene, bpy.context.view_layer) as shift:
        assert shift is not None and abs(shift.x - FAR) < 1.0 and shift.z == 0.0
        assert shape_error(fine) < 0.00005, shape_error(fine)
        camera = bpy.data.objects["eye"].matrix_world.translation
        assert max(abs(camera.x), abs(camera.y)) < 1.0 and abs(camera.z - 13.0) < 1e-4


def test_render_commands_run_camera_relative_and_put_everything_back(bridge):
    far_scene(bridge)
    before = {obj.name: obj.matrix_basis.copy() for obj in bpy.data.objects}
    seen = []

    def note(scene, *rest):
        seen.append(tuple(bpy.data.objects["eye"].matrix_world.translation))

    bpy.app.handlers.render_pre.append(note)
    try:
        final = bridge.ok("render_final", path="far.png", camera="eye", width=32, height=32, samples=1, device="cpu", preview=False)
        preview = bridge.ok("render_preview", camera="eye", resolution=64, samples=1, device="cpu")
    finally:
        bpy.app.handlers.render_pre.remove(note)
    assert seen and all(max(abs(x), abs(y)) < 1.0 for x, y, _ in seen), seen
    assert {obj.name: obj.matrix_basis.copy() for obj in bpy.data.objects} == before
    for reply in (final, preview):
        assert reply["camera_relative"] == [{"camera": "eye", "shift": [FAR, -FAR, 0.0]}], reply["camera_relative"]


def test_near_cameras_render_in_place(bridge):
    assert floating_origin.shift_for(None) is None
    assert floating_origin.shift_for(Vector((limits.SAFE_CAMERA_DISTANCE * 0.99, 0.0, 0.0))) is None
    shift = floating_origin.shift_for(Vector((limits.SAFE_CAMERA_DISTANCE * 2.0 + 0.4, -3.6, 900.0)))
    assert tuple(shift) == (limits.SAFE_CAMERA_DISTANCE * 2.0, -4.0, 0.0)


def cube_scene(bridge):
    bridge.ok("new_scene")
    bridge.ok("add_camera", name="cam", location=[FAR, 0.0, 2.0], target=[FAR, 10.0, 2.0])
    bridge.ok("camera_setup", name="cam", clip_end=1000.0)
    bridge.ok("add_light", type="sun", name="sun")


def cube(bridge, name, location):
    bridge.ok("add_primitive", type="cube", name=name, location=list(location), size=2.0)
    return bpy.data.objects[name]


def add_static(bridge):
    cube(bridge, "a", (FAR, 10.0, 2.0))


def add_animated(bridge):
    obj = cube(bridge, "b", (FAR, 10.0, 2.0))
    obj.keyframe_insert("location", frame=1)
    obj.location.x = FAR + 0.5
    obj.keyframe_insert("location", frame=10)


def add_child_of(bridge):
    anchor = bpy.data.objects.new("anchor", None)
    bpy.context.scene.collection.objects.link(anchor)
    anchor.location = (FAR, 10.0, 2.0)
    constraint = cube(bridge, "c", (0.0, 0.0, 0.0)).constraints.new("CHILD_OF")
    constraint.target = anchor
    constraint.inverse_matrix.identity()


def add_driven(bridge):
    curve = cube(bridge, "d", (FAR, 10.0, 2.0)).driver_add("location", 0)
    curve.driver.expression = "150000.0"


def add_instanced(bridge):
    source = bpy.data.collections.new("src")
    bpy.context.scene.collection.children.link(source)
    mesh = bpy.data.meshes.new("srcm")
    shape = bmesh.new()
    bmesh.ops.create_cube(shape, size=2.0)
    shape.to_mesh(mesh)
    shape.free()
    source.objects.link(bpy.data.objects.new("srcobj", mesh))
    bpy.context.view_layer.layer_collection.children["src"].exclude = True
    instance = bpy.data.objects.new("inst", None)
    instance.instance_type = "COLLECTION"
    instance.instance_collection = source
    instance.location = (FAR, 10.0, 2.0)
    bpy.context.scene.collection.objects.link(instance)


def add_limited(bridge):
    constraint = cube(bridge, "f", (FAR, 10.0, 2.0)).constraints.new("LIMIT_LOCATION")
    constraint.use_min_x = True
    constraint.min_x = FAR - 100.0


def add_offset_copy(bridge):
    target = bpy.data.objects.new("t", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (FAR, 0.0, 0.0)
    constraint = cube(bridge, "g", (0.0, 10.0, 2.0)).constraints.new("COPY_LOCATION")
    constraint.target = target
    constraint.use_offset = True


def clay(bridge, name):
    reply = bridge.ok("render_final", path=name + ".exr", camera="cam", width=SIZE, height=SIZE, samples=1, preview=False, shading="clay", device="cpu", denoise=False)
    pixels = numpy.asarray(exr_read.read_exr(os.path.join(bridge.workspace, name + ".exr")).stack("", "RGB"), dtype=numpy.float64) @ LUMINANCE
    return pixels, reply.get("camera_relative")


def same_as_unshifted(bridge, name, add):
    """Render the cube scene add completes with the world moved and, as the control, without; both must agree."""
    cube_scene(bridge)
    add(bridge)
    with Unshifted():
        control, unmoved = clay(bridge, name + "_control")
    cube_scene(bridge)
    add(bridge)
    moved, notes = clay(bridge, name)
    assert unmoved is None, unmoved
    brightest = float(control.max())
    assert abs(control[SIZE // 2, SIZE // 2] - control[2, 2]) > CONTRAST * brightest, f"{name}: the control should show the cube"
    differing = int((numpy.abs(moved - control) > CHANGED * brightest).sum())
    assert differing <= EDGE_PIXELS, f"{name}: {differing} pixels differ from the unshifted control; notes {notes}"
    return notes


def moved_by_far(notes):
    return notes == [{"camera": "cam", "shift": [FAR, 0.0, 0.0]}]


def test_a_static_cube_renders_moved_as_unmoved(bridge):
    assert moved_by_far(same_as_unshifted(bridge, "a", add_static))


def test_b_keyframed_location_renders_moved_as_unmoved(bridge):
    assert moved_by_far(same_as_unshifted(bridge, "b", add_animated))


def test_c_child_of_renders_moved_as_unmoved(bridge):
    assert moved_by_far(same_as_unshifted(bridge, "c", add_child_of))


def test_d_driven_location_renders_moved_as_unmoved(bridge):
    assert moved_by_far(same_as_unshifted(bridge, "d", add_driven))


def test_e_instance_of_an_excluded_collection_renders_moved_as_unmoved(bridge):
    assert moved_by_far(same_as_unshifted(bridge, "e", add_instanced))


def test_f_world_limit_location_renders_moved_as_unmoved(bridge):
    assert moved_by_far(same_as_unshifted(bridge, "f", add_limited))


def test_a_constraint_no_frame_follows_keeps_the_origin_and_says_why(bridge):
    notes = same_as_unshifted(bridge, "g", add_offset_copy)
    assert len(notes) == 1 and "shift" not in notes[0] and "g does not follow" in notes[0]["kept_origin"], notes


def cloud_scene(bridge, form):
    bridge.ok("new_scene")
    bridge.ok("add_primitive", type="plane", name="Ground", size=9000.0, location=[FAR, 0.0, 0.0])
    bridge.ok("add_material", name="Grey", base_color=[0.3, 0.3, 0.3], roughness=1.0)
    bridge.ok("assign_material", name="Ground", material="Grey")
    bridge.ok("add_camera", name="Top", location=[FAR, 0.0, 400.0], rotation=[0.0, 0.0, 0.0], orthographic_scale=6000.0)
    bpy.data.objects["Top"].data.clip_end = 100_000.0
    bridge.ok("sky", sun={"elevation": 70.0, "azimuth": 180.0}, exposure="keep")
    bridge.ok("clouds", layers=[{"genus": "cumulus", "coverage": 0.5, "thickness": 600.0, "seed": 2}], form=form, radius=6000.0, bounces=1)


def cloud_ground(bridge, name):
    reply = bridge.ok("render_final", path=name + ".exr", camera="Top", width=48, height=48, samples=4, denoise=False,
                      noise_threshold=0.0, time_limit=600.0, preview=False, device="cpu")
    pixels = numpy.asarray(exr_read.read_exr(os.path.join(bridge.workspace, name + ".exr")).stack("", "RGB"), dtype=numpy.float64)
    return pixels @ LUMINANCE, reply.get("camera_relative")


def test_cloud_shadows_and_volumes_fall_where_they_fall_unmoved(bridge):
    for form in ("sheet", "volume"):
        cloud_scene(bridge, form)
        with Unshifted():
            control, _ = cloud_ground(bridge, form + "_control")
        cloud_scene(bridge, form)
        moved, notes = cloud_ground(bridge, form)
        assert notes == [{"camera": "Top", "shift": [FAR, 0.0, 0.0]}], notes
        assert numpy.percentile(control, 95) > 2.0 * numpy.percentile(control, 5), "the control should show cloud shadows"
        mismatch = float(numpy.abs(moved - control).mean() / control.mean())
        assert mismatch < CLOUD_MATCH, (form, mismatch)


def test_previews_without_a_camera_render_where_the_subject_is(bridge):
    fine_mesh(bridge, [0.3217, 0.6061, 0.5])
    bridge.ok("add_camera", name="faraway", location=[FAR, 0.0, 2.0], target=[FAR, 10.0, 2.0])
    bpy.context.scene.camera = bpy.data.objects["faraway"]
    errors = []

    def measure(scene, *rest):
        errors.append(shape_error(bpy.data.objects["fine"]))

    bpy.app.handlers.render_pre.append(measure)
    try:
        turntable = bridge.ok("render_preview", views=["front", "top"], resolution=64, samples=1, device="cpu")
        close_up = bridge.ok("render_preview", focus={"object": "fine"}, resolution=64, samples=1, device="cpu")
    finally:
        bpy.app.handlers.render_pre.remove(measure)
    assert len(errors) == 3 and max(errors) < 0.00005, errors
    assert "camera_relative" not in turntable and "camera_relative" not in close_up
    assert bpy.context.scene.camera.name == "faraway"


def matrix(value):
    return tuple(map(tuple, value))


def constraint_state(constraint):
    if constraint.type == "CHILD_OF":
        return matrix(constraint.inverse_matrix)
    if constraint.type == "LIMIT_LOCATION":
        return tuple(getattr(constraint, key) for key in ("min_x", "max_x", "min_y", "max_y"))
    return None


def state():
    """Everything the move touches, exactly."""
    objects = {}
    for obj in bpy.data.objects:
        objects[obj.name] = (obj.parent.name if obj.parent else None, obj.parent_type, obj.parent_bone,
                             matrix(obj.matrix_parent_inverse), matrix(obj.matrix_basis), matrix(obj.matrix_world),
                             [(c.name, c.type, constraint_state(c)) for c in obj.constraints])
    trees = {}
    for material in bpy.data.materials:
        tree = material.node_tree
        links = sorted((link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier, link.is_muted) for link in tree.links)
        defaults = sorted((node.name, tuple(node.inputs[0].default_value)) for node in tree.nodes if node.bl_idname == "ShaderNodeVectorTransform")
        trees[material.name] = (sorted(node.name for node in tree.nodes), links, defaults)
    offsets = {collection.name: tuple(collection.instance_offset) for collection in bpy.data.collections}
    return objects, trees, offsets


def busy_scene(bridge):
    cube_scene(bridge)
    add_child_of(bridge)
    limited = bpy.data.objects["c"].constraints.new("LIMIT_LOCATION")
    limited.owner_space = "WORLD"
    limited.use_min_y = True
    limited.min_y = 3.3333
    add_instanced(bridge)
    bpy.data.collections["src"].instance_offset = (0.3, -1.25, 0.5)
    add_animated(bridge)
    bridge.ok("add_empty", name="kid", location=[1.0, 2.0, 3.0], parent="b")
    bpy.data.objects["b"].matrix_parent_inverse = Matrix.Translation((0.125, 0.0, 0.0))
    material = bpy.data.materials.new("worldly")
    tree = material.node_tree
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    tree.links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    transform = tree.nodes.new("ShaderNodeVectorTransform")
    transform.vector_type = "POINT"
    transform.convert_from = "WORLD"
    transform.convert_to = "OBJECT"
    transform.inputs[0].default_value = (FAR + 0.0078125, 10.3333, 2.0)
    tree.links.new(transform.outputs[0], tree.nodes["Principled BSDF"].inputs["Base Color"])
    bpy.data.objects["b"].data.materials.append(material)
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)


def test_the_move_puts_back_every_value_exactly_after_a_render_and_after_a_failure(bridge):
    busy_scene(bridge)
    before = state()
    names = sorted(bpy.data.objects.keys())
    scene = bpy.context.scene
    scene.camera = bpy.data.objects["cam"]
    with floating_origin.camera_relative(scene, bpy.context.view_layer) as shift:
        assert shift is not None and state() != before
    assert state() == before
    try:
        with floating_origin.camera_relative(scene, bpy.context.view_layer):
            raise RuntimeError("render failed")
    except RuntimeError:
        pass
    assert state() == before and sorted(bpy.data.objects.keys()) == names
    assert not any(floating_shaders.NODE_NAME in node.name for tree in floating_shaders.shader_trees() for node in tree.nodes)
    reply = bridge.ok("render_final", path="busy.png", camera="cam", width=32, height=32, samples=1, preview=False, device="cpu")
    assert reply["camera_relative"] == [{"camera": "cam", "shift": [FAR, 0.0, 0.0]}], reply["camera_relative"]
    assert state() == before and sorted(bpy.data.objects.keys()) == names


run(globals())
