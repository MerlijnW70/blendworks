import os
import sys

import bmesh
import bpy

WIDTH = 1.0
DEPTH = 1.0
HEIGHT = 0.8


def output_folder():
    return sys.argv[sys.argv.index("--") + 1]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mesh_object(name, vertices, faces, edges=()):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, list(edges), faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def box_geometry(width, depth, height, centre=(0.0, 0.0, 0.0), lifted=True):
    x, y, z = centre
    bottom = z if lifted else z - height / 2
    corners = [
        (x + sx * width / 2, y + sy * depth / 2, bottom + sz * height)
        for sz in (0, 1)
        for sy in (-1, 1)
        for sx in (-1, 1)
    ]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    return corners, faces


def crate_box(name="Crate"):
    vertices, faces = box_geometry(WIDTH, DEPTH, HEIGHT)
    obj = mesh_object(name, vertices, faces)
    cross_uv(obj.data)
    return obj


def cross_uv(mesh, offsets=None):
    layer = mesh.uv_layers.new(name="UVMap")
    cells = [(1, 0), (1, 2), (1, 1), (1, 3), (0, 1), (2, 1)]
    for polygon in mesh.polygons:
        column, row = cells[polygon.index % len(cells)]
        shift = offsets[polygon.index] if offsets else 0
        corners = ((0, 0), (1, 0), (1, 1), (0, 1))
        for (du, dv), loop in zip(corners, polygon.loop_indices):
            layer.uv[loop].vector = ((column + du) * 0.25 + shift, (row + dv) * 0.25)


def material(name):
    created = bpy.data.materials.new(name)
    return created


def export_glb(folder, name):
    bpy.ops.export_scene.gltf(filepath=os.path.join(folder, name), export_format="GLB", export_apply=True)


def save_blend(folder, name):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, name), check_existing=False)


def instanced(folder):
    reset()
    body_vertices, body_faces = box_geometry(1.2, 0.6, 0.3, (0.0, 0.0, 0.25))
    body = mesh_object("Body", body_vertices, body_faces)
    cross_uv(body.data)
    body.data.materials.append(material("paint"))
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.15, depth=0.08, rotation=(1.5707963, 0.0, 0.0))
    wheel = bpy.context.active_object
    wheel.name = "Wheel.000"
    wheel.data.name = "wheel"
    wheel.data.materials.append(material("rubber"))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    for loop in wheel.data.uv_layers.active.uv:
        loop.vector = (0.75 + loop.vector[0] * 0.25, loop.vector[1] * 0.25)
    places = [(-0.4, -0.34, 0.15), (0.4, -0.34, 0.15), (-0.4, 0.34, 0.15), (0.4, 0.34, 0.15)]
    wheel.location = places[0]
    for index, place in enumerate(places[1:], start=1):
        copy = wheel.copy()
        copy.name = f"Wheel.{index:03d}"
        copy.location = place
        bpy.context.scene.collection.objects.link(copy)
    export_glb(folder, "instanced.glb")


def animated(folder):
    for frame in (1, 40):
        reset()
        obj = crate_box()
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.keyframe_insert("location", frame=1)
        obj.keyframe_insert("rotation_euler", frame=1)
        obj.location = (2.0, 0.0, 1.5)
        obj.rotation_euler = (0.0, 0.7, 0.4)
        obj.keyframe_insert("location", frame=40)
        obj.keyframe_insert("rotation_euler", frame=40)
        bpy.context.scene.frame_set(frame)
        save_blend(folder, f"animated-{frame}.blend")


def centimetres(folder):
    reset()
    bpy.context.scene.unit_settings.scale_length = 0.01
    vertices, faces = box_geometry(100.0, 100.0, 80.0)
    obj = mesh_object("Crate", vertices, faces)
    cross_uv(obj.data)
    obj.location = (50.0, 0.0, 0.0)
    save_blend(folder, "centimetres.blend")


def padded(folder):
    reset()
    crate_box()
    for index in range(20):
        column, row = index % 5, index // 5
        vertices, faces = box_geometry(0.1, 0.1, 0.1, (-0.36 + column * 0.18, -0.3 + row * 0.15, 0.3))
        mesh_object(f"Filler.{index:03d}", vertices, faces)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = bpy.data.objects["Crate"]
    bpy.ops.object.join()
    export_glb(folder, "padded.glb")


def joined(extra_vertices, extra_faces, extra_edges=()):
    reset()
    vertices, faces = box_geometry(WIDTH, DEPTH, HEIGHT)
    offset = len(vertices)
    shifted = [tuple(index + offset for index in face) for face in extra_faces]
    edges = [tuple(index + offset for index in edge) for edge in extra_edges]
    obj = mesh_object("Crate", vertices + list(extra_vertices), faces + shifted, edges)
    cross_uv(obj.data)
    return obj


def degenerate(folder):
    joined([(-0.2, 0.0, 0.4), (0.0, 0.0, 0.4), (0.2, 0.0, 0.4)], [(0, 1, 2)])
    export_glb(folder, "degenerate.glb")


def duplicate(folder):
    lid = [(-0.5, -0.5, 0.8), (-0.5, 0.5, 0.8), (0.5, 0.5, 0.8), (0.5, -0.5, 0.8)]
    joined(lid, [(0, 3, 2, 1)])
    save_blend(folder, "duplicate.blend")


def inverted(folder):
    reset()
    obj = crate_box()
    graph = bmesh.new()
    graph.from_mesh(obj.data)
    bmesh.ops.reverse_faces(graph, faces=graph.faces[:])
    graph.to_mesh(obj.data)
    graph.free()
    export_glb(folder, "inverted.glb")


def tiny_shells(folder):
    reset()
    crate_box()
    for index, x in enumerate((-0.3, -0.1, 0.1, 0.3)):
        vertices, faces = box_geometry(0.01, 0.01, 0.01, (x, 0.0, 0.8))
        mesh_object(f"Speck.{index}", vertices, faces)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = bpy.data.objects["Crate"]
    bpy.ops.object.join()
    export_glb(folder, "tiny-shells.glb")


def loose_vertex(folder):
    joined([(5.0, 5.0, 5.0), (-4.0, 0.0, 0.0), (-4.0, 0.0, 3.0)], [], [(1, 2)])
    save_blend(folder, "loose-vertex.blend")


def wrapped_uv(folder):
    reset()
    vertices, faces = box_geometry(WIDTH, DEPTH, HEIGHT)
    obj = mesh_object("Crate", vertices, faces)
    layer = obj.data.uv_layers.new(name="UVMap")
    for polygon in obj.data.polygons:
        for (du, dv), loop in zip(((0, 0), (1, 0), (1, 1), (0, 1)), polygon.loop_indices):
            layer.uv[loop].vector = (0.25 + 0.25 * du + polygon.index, 0.25 + 0.25 * dv)
    export_glb(folder, "wrapped-uv.glb")


def modifier_bombs(folder):
    reset()
    obj = crate_box()
    array = obj.modifiers.new("Array", "ARRAY")
    array.count = 1000
    second = obj.modifiers.new("Array2", "ARRAY")
    second.count = 1000
    second.relative_offset_displace = (0.0, 1.0, 0.0)
    save_blend(folder, "array-bomb.blend")
    obj.modifiers.clear()
    obj.modifiers.new("Nodes", "NODES")
    save_blend(folder, "geometry-nodes.blend")


def textured_files(folder):
    reset()
    obj = crate_box()
    image = bpy.data.images.new("wood", 8, 8)
    image.filepath_raw = os.path.join(folder, "wood.png")
    image.file_format = "PNG"
    image.save()
    wood = bpy.data.materials.new("wood")
    texture = wood.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    shader = next(node for node in wood.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    wood.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    obj.data.materials.append(wood)
    bpy.ops.wm.obj_export(filepath=os.path.join(folder, "textured.obj"), path_mode="RELATIVE")
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "textured.fbx"), path_mode="RELATIVE")
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "embedded.fbx"), path_mode="COPY", embed_textures=True)
    image.filepath_raw = os.path.join(folder, "missing.png")
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "missing.fbx"), path_mode="RELATIVE")


def main():
    folder = output_folder()
    os.makedirs(folder, exist_ok=True)
    instanced(folder)
    animated(folder)
    centimetres(folder)
    padded(folder)
    degenerate(folder)
    duplicate(folder)
    inverted(folder)
    tiny_shells(folder)
    loose_vertex(folder)
    wrapped_uv(folder)
    modifier_bombs(folder)
    textured_files(folder)


main()
