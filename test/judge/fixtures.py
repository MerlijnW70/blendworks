FIXTURE_DEPS = ()
import os
import sys

import bmesh
import bpy
from mathutils import Matrix

WIDTH = 1.0
DEPTH = 1.0
HEIGHT = 0.8


def arguments():
    rest = sys.argv[sys.argv.index("--") + 1 :]
    return rest[0], rest[1]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, colour, metallic, roughness):
    created = bpy.data.materials.new(name)
    shader = next(node for node in created.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (*colour, 1.0)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return created


def box(name, width=WIDTH, depth=DEPTH, height=HEIGHT, bottom_origin=True):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    lift = height / 2 if bottom_origin else 0.0
    obj.data.transform(Matrix.Translation((0.0, 0.0, lift)) @ Matrix.Diagonal((width, depth, height, 1.0)))
    obj.data.materials.append(material("wood", (0.42, 0.26, 0.13), 0.0, 0.7))
    obj.data.materials.append(material("metal", (0.62, 0.63, 0.66), 1.0, 0.35))
    for polygon in obj.data.polygons:
        polygon.material_index = 1 if abs(polygon.normal.z) > 0.5 else 0
    return obj


def export_glb(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True)


def save_blend(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)


def crate(folder):
    reset()
    box("Crate")
    export_glb(os.path.join(folder, "crate.glb"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(folder, "crate.gltf"), export_format="GLTF_SEPARATE", export_apply=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "crate.fbx"))
    bpy.ops.wm.obj_export(filepath=os.path.join(folder, "crate.obj"))
    save_blend(os.path.join(folder, "crate.blend"))


def over_budget(folder):
    reset()
    obj = box("Crate")
    modifier = obj.modifiers.new("Subdivision", "SUBSURF")
    modifier.subdivision_type = "SIMPLE"
    modifier.levels = 2
    modifier.render_levels = 2
    save_blend(os.path.join(folder, "over-budget.blend"))


def wrong_size(folder):
    reset()
    box("Crate", width=2.0)
    export_glb(os.path.join(folder, "wrong-size.glb"))


def centre_origin(folder):
    reset()
    box("Crate", bottom_origin=False)
    export_glb(os.path.join(folder, "centre-origin.glb"))


def open_box(folder):
    reset()
    obj = box("Crate")
    graph = bmesh.new()
    graph.from_mesh(obj.data)
    top = [face for face in graph.faces if face.normal.z > 0.5]
    bmesh.ops.delete(graph, geom=top, context="FACES_ONLY")
    graph.to_mesh(obj.data)
    graph.free()
    export_glb(os.path.join(folder, "open-box.glb"))


def no_uv(folder):
    reset()
    obj = box("Crate")
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[0])
    export_glb(os.path.join(folder, "no-uv.glb"))


def overlapping_uv(folder):
    reset()
    obj = box("Crate")
    corners = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    layer = obj.data.uv_layers.active
    for polygon in obj.data.polygons:
        for corner, loop_index in zip(corners, polygon.loop_indices):
            layer.uv[loop_index].vector = corner
    export_glb(os.path.join(folder, "overlap-uv.glb"))


def autorun(folder, marker_folder):
    reset()
    obj = box("Crate")
    text = bpy.data.texts.new("autorun.py")
    text_marker = os.path.join(marker_folder, "autorun-text.marker")
    text.write(f"import pathlib\npathlib.Path({text_marker!r}).write_text('ran')\n")
    text.use_module = True
    driver_marker = os.path.join(marker_folder, "autorun-driver.marker")
    bpy.data.texts.new("driver_marker").write(driver_marker)
    curve = obj.driver_add("location", 0)
    curve.driver.type = "SCRIPTED"
    curve.driver.expression = "__import__('pathlib').Path(bpy.data.texts['driver_marker'].as_string()).write_text('ran') and 0"
    save_blend(os.path.join(folder, "autorun.blend"))
    for marker in (text_marker, driver_marker):
        if os.path.exists(marker):
            os.remove(marker)


def main():
    folder, marker_folder = arguments()
    os.makedirs(folder, exist_ok=True)
    crate(folder)
    over_budget(folder)
    wrong_size(folder)
    centre_origin(folder)
    open_box(folder)
    no_uv(folder)
    overlapping_uv(folder)
    autorun(folder, marker_folder)


main()
