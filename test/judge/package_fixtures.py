FIXTURE_DEPS = ()
import os
import sys

import bmesh
import bpy

SEGMENTS = 64
RINGS = 32


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def picture(name, size, colour, data, pattern="BLANK"):
    created = bpy.data.images.new(name, size, size)
    created.generated_type = pattern
    created.generated_color = colour
    if data:
        created.colorspace_settings.name = "Non-Color"
    created.pack()
    return created


def textured_material(name):
    material = bpy.data.materials.new(name)
    tree = material.node_tree
    shader = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")

    def texture(image):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        return node

    tree.links.new(texture(picture(f"{name}-base", 128, (0.7, 0.45, 0.2, 1.0), False, "COLOR_GRID")).outputs["Color"], shader.inputs["Base Color"])
    split = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(texture(picture(f"{name}-orm", 64, (1.0, 0.5, 0.0, 1.0), True)).outputs["Color"], split.inputs["Color"])
    tree.links.new(split.outputs["Green"], shader.inputs["Roughness"])
    tree.links.new(split.outputs["Blue"], shader.inputs["Metallic"])
    normal_map = tree.nodes.new("ShaderNodeNormalMap")
    tree.links.new(texture(picture(f"{name}-normal", 64, (0.5, 0.5, 1.0, 1.0), True)).outputs["Color"], normal_map.inputs["Color"])
    tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])
    return material


def plain_material(name, colour):
    material = bpy.data.materials.new(name)
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (*colour, 1.0)
    return material


def export(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True)


def textured_ball(folder):
    reset()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=SEGMENTS, ring_count=RINGS, location=(0.0, 0.0, 0.5))
    ball = bpy.context.active_object
    ball.name = "Ball"
    bpy.ops.object.shade_smooth()
    ball.data.materials.append(textured_material("painted"))
    export(os.path.join(folder, "textured-ball.glb"))


def rig(folder):
    reset()
    group = bpy.data.objects.new("Rig", None)
    bpy.context.scene.collection.objects.link(group)
    group.location = (0.5, 0.0, 0.0)
    for index, (name, colour) in enumerate((("Arm", (0.7, 0.2, 0.2)), ("Hand", (0.2, 0.2, 0.7)))):
        bpy.ops.mesh.primitive_cube_add(size=0.4, location=(index * 0.6, 0.0, 0.2))
        part = bpy.context.active_object
        part.name = name
        builder = bmesh.new()
        builder.from_mesh(part.data)
        bmesh.ops.subdivide_edges(builder, edges=builder.edges[:], cuts=10, use_grid_fill=True)
        builder.to_mesh(part.data)
        builder.free()
        part.data.materials.append(plain_material(f"{name}-paint", colour))
        part.parent = group
        part.matrix_parent_inverse = group.matrix_world.inverted()
    export(os.path.join(folder, "rig.glb"))


def thin_ring(folder):
    reset()
    bpy.ops.mesh.primitive_torus_add(major_radius=0.5, minor_radius=0.01, major_segments=96, minor_segments=12, location=(0.0, 0.0, 0.5))
    bpy.context.active_object.name = "Ring"
    bpy.context.active_object.data.materials.append(plain_material("thread", (0.8, 0.8, 0.2)))
    export(os.path.join(folder, "thin-ring.glb"))


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    textured_ball(folder)
    rig(folder)
    thin_ring(folder)


main()
