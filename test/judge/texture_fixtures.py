FIXTURE_DEPS = ()
import json
import os
import struct
import sys

import bmesh
import bpy
from mathutils import Matrix

GLB_JSON = 0x4E4F534A


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def image(name, width, height, colour, data, pattern="BLANK"):
    created = bpy.data.images.new(name, width, height)
    created.generated_type = pattern
    created.generated_color = colour
    if data:
        created.colorspace_settings.name = "Non-Color"
    created.pack()
    return created


def occlusion_group():
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return group


def textured_material(name, maps, with_normal=True):
    material = bpy.data.materials.new(name)
    tree = material.node_tree
    shader = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")

    def texture(picture):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = picture
        return node

    tree.links.new(texture(maps["base"]).outputs["Color"], shader.inputs["Base Color"])
    split = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(texture(maps["orm"]).outputs["Color"], split.inputs["Color"])
    tree.links.new(split.outputs["Green"], shader.inputs["Roughness"])
    tree.links.new(split.outputs["Blue"], shader.inputs["Metallic"])
    output_group = tree.nodes.new("ShaderNodeGroup")
    output_group.node_tree = occlusion_group()
    tree.links.new(split.outputs["Red"], output_group.inputs["Occlusion"])
    if with_normal:
        normal_map = tree.nodes.new("ShaderNodeNormalMap")
        tree.links.new(texture(maps["normal"]).outputs["Color"], normal_map.inputs["Color"])
        tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    tree.links.new(texture(maps["emit"]).outputs["Color"], shader.inputs["Emission Color"])
    shader.inputs["Emission Strength"].default_value = 1.0
    return material


def textured_box(base_size=(64, 64), with_normal=True):
    reset()
    shared = {
        "orm": image("orm", 32, 32, (1.0, 0.5, 0.0, 1.0), True),
        "normal": image("normal", 64, 64, (0.5, 0.5, 1.0, 1.0), True),
        "emit": image("emit", 16, 16, (0.0, 0.0, 0.0, 1.0), False),
    }
    painted = textured_material("painted", {**shared, "base": image("base", *base_size, (0.6, 0.4, 0.2, 1.0), False, "COLOR_GRID")}, with_normal)
    trim = textured_material("trim", {**shared, "base": image("base_trim", 32, 32, (0.5, 0.5, 0.55, 1.0), False, "UV_GRID")}, with_normal)
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.active_object
    obj.name = "Box"
    obj.data.transform(Matrix.Translation((0.0, 0.0, 0.5)))
    obj.data.materials.append(painted)
    obj.data.materials.append(trim)
    for polygon in obj.data.polygons:
        polygon.material_index = 1 if abs(polygon.normal.z) > 0.5 else 0
    return obj


def export_glb(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_tangents=True)


def textured(folder):
    textured_box()
    export_glb(os.path.join(folder, "textured.glb"))
    external = os.path.join(folder, "external")
    os.makedirs(external, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(external, "external.gltf"), export_format="GLTF_SEPARATE", export_tangents=True)
    bpy.data.images["normal"].colorspace_settings.name = "sRGB"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, "wrong-colour.blend"), check_existing=False)


def missing_normal(folder):
    textured_box(with_normal=False)
    export_glb(os.path.join(folder, "missing-normal.glb"))


def non_power_of_two(folder):
    textured_box(base_size=(48, 20))
    export_glb(os.path.join(folder, "npot.glb"))


def read_glb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    return document, data[20 + json_length :]


def write_glb(path, document, rest):
    text = json.dumps(document, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(text) + len(rest))
    with open(path, "wb") as handle:
        handle.write(header + struct.pack("<II", len(text), GLB_JSON) + text + rest)


def plain(folder):
    reset()
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    path = os.path.join(folder, "plain.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB")
    document, rest = read_glb(path)
    position = document["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
    wrong_bounds = json.loads(json.dumps(document))
    wrong_bounds["accessors"][position]["max"] = [2.0, 2.0, 2.0]
    write_glb(os.path.join(folder, "wrong-bounds.glb"), wrong_bounds, rest)
    overrun = json.loads(json.dumps(document))
    indices = overrun["meshes"][0]["primitives"][0]["indices"]
    overrun["accessors"][indices]["count"] = 3_000_000
    write_glb(os.path.join(folder, "overrun.glb"), overrun, rest)


def boxes(name, corners):
    mesh = bpy.data.meshes.new(name)
    graph = bmesh.new()
    for low, high in corners:
        size = [high[axis] - low[axis] for axis in range(3)]
        centre = [(high[axis] + low[axis]) / 2 for axis in range(3)]
        matrix = Matrix.Translation(centre) @ Matrix.Diagonal((*size, 1.0))
        bmesh.ops.create_cube(graph, size=1.0, matrix=matrix)
    graph.to_mesh(mesh)
    graph.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def parts_scene(path, stray, lamp):
    reset()
    base = ((-0.5, -0.5, 0.0), (0.5, 0.5, 0.5))
    top = ((-0.25, -0.25, 0.5), (0.25, 0.25, 0.8))
    boxes("Body", [base, top, stray])
    boxes("Lamp", [lamp])
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB")


def floating(folder):
    parts_scene(os.path.join(folder, "floating.glb"), ((1.0, -0.1, 0.0), (1.2, 0.1, 0.2)), ((-0.1, -0.1, 1.3), (0.1, 0.1, 1.5)))
    parts_scene(os.path.join(folder, "touching.glb"), ((0.5, -0.1, 0.0), (0.7, 0.1, 0.2)), ((-0.1, -0.1, 0.8), (0.1, 0.1, 1.0)))
    parts_scene(os.path.join(folder, "near.glb"), ((0.5, -0.1, 0.0), (0.7, 0.1, 0.2)), ((-0.1, -0.1, 0.8005), (0.1, 0.1, 1.0005)))


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    textured(folder)
    missing_normal(folder)
    non_power_of_two(folder)
    plain(folder)
    floating(folder)


main()
