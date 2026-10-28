FIXTURE_DEPS = ()
import math
import os
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

STAND_INS = ("uv-sphere", "clouds-ico", "jittered-ico", "cylinder-tree")


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def export_glb(folder, name):
    bpy.ops.export_scene.gltf(filepath=os.path.join(folder, f"{name}.glb"), export_format="GLB")


def mesh_object(name, bm):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def apply_modifiers(obj):
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def scaled(obj, factors):
    obj.data.transform(Matrix.Diagonal((*factors, 1.0)))


def uv_sphere(segments=128, rings=64):
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=0.5, calc_uvs=True)
    return mesh_object("Sphere", bm)


def ico_sphere(name, subdivisions):
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=0.5, calc_uvs=True)
    return mesh_object(name, bm)


def displace(obj, texture_type, strength, **settings):
    texture = bpy.data.textures.new(f"{obj.name}-{texture_type.lower()}", texture_type)
    for key, value in settings.items():
        setattr(texture, key, value)
    modifier = obj.modifiers.new("Displace", "DISPLACE")
    modifier.texture = texture
    modifier.texture_coords = "LOCAL"
    modifier.strength = strength
    apply_modifiers(obj)


def clouds_ico():
    obj = ico_sphere("CloudsIco", 5)
    displace(obj, "CLOUDS", 0.25, noise_scale=0.4)
    scaled(obj, (1.0, 0.8, 0.6))
    return obj


def jittered_ico():
    obj = ico_sphere("JitteredIco", 1)
    rng = random.Random(15)
    for vertex in obj.data.vertices:
        vertex.co = vertex.co * (1.0 + rng.uniform(-0.15, 0.15))
    scaled(obj, (1.0, 0.75, 0.55))
    return obj


def cylinder(bm, start, end, radius):
    axis = end - start
    length = axis.length
    matrix = Matrix.Translation((start + end) / 2) @ axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=radius, radius2=radius * 0.7, depth=length, matrix=matrix)


def cylinder_tree():
    bm = bmesh.new()
    trunk_top = Vector((0.0, 0.0, 1.2))
    cylinder(bm, Vector((0.0, 0.0, 0.0)), trunk_top, 0.08)
    for branch in range(3):
        angle = branch * 2.0 * math.pi / 3.0
        tip = trunk_top + Vector((math.cos(angle) * 0.6, math.sin(angle) * 0.6, 0.5))
        cylinder(bm, trunk_top, tip, 0.04)
        for twig in range(12):
            turn = angle + (twig - 5.5) * 0.25
            base = trunk_top.lerp(tip, 0.3 + 0.06 * twig)
            cylinder(bm, base, base + Vector((math.cos(turn) * 0.3, math.sin(turn) * 0.3, 0.25)), 0.012)
    return mesh_object("CylinderTree", bm)


def cube():
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    return mesh_object("Cube", bm)


def value_noise(size, seed, octaves=6):
    rng = np.random.default_rng(seed)
    field = np.zeros((size, size))
    amplitude = 1.0
    for octave in range(octaves):
        cells = 4 * 2**octave
        lattice = rng.random((cells + 1, cells + 1))
        lattice[-1, :] = lattice[0, :]
        lattice[:, -1] = lattice[:, 0]
        position = np.arange(size) * cells / size
        index = position.astype(int)
        fraction = position - index
        smooth = fraction * fraction * (3 - 2 * fraction)
        rows = lattice[index] * (1 - smooth)[:, None] + lattice[index + 1] * smooth[:, None]
        field += amplitude * (rows[:, index] * (1 - smooth)[None, :] + rows[:, index + 1] * smooth[None, :])
        amplitude *= 0.6
    field -= field.min()
    return field / field.max()


def packed_image(name, grey, alpha=None):
    height, width = grey.shape
    image = bpy.data.images.new(name, width, height, alpha=alpha is not None)
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = grey[:, :, None]
    if alpha is not None:
        rgba[:, :, 3] = alpha
    image.pixels.foreach_set(rgba.ravel())
    image.pack()
    return image


def textured(obj, image, cutout=False):
    material = bpy.data.materials.new(f"{obj.name}-material")
    tree = material.node_tree
    shader = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
    if cutout:
        tree.links.new(node.outputs["Alpha"], shader.inputs["Alpha"])
    obj.data.materials.append(material)


def unit_plane():
    bm = bmesh.new()
    layer = bm.loops.layers.uv.new("UVMap")
    corners = [bm.verts.new(point) for point in ((-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0))]
    face = bm.faces.new(corners)
    for loop, uv in zip(face.loops, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        loop[layer].uv = uv
    return mesh_object("Plane", bm)


def upright_card(cutout):
    obj = unit_plane()
    obj.data.transform(Matrix.Rotation(math.radians(90), 4, "X"))
    alpha = np.ones((64, 64))
    alpha[:, :32] = 0.0
    textured(obj, packed_image("card", np.full((64, 64), 0.5), alpha if cutout else None), cutout)
    return obj


def two_tone(size=64, dark_columns=16, dark=0.2, light=0.6):
    grey = np.full((size, size), light)
    grey[:, :dark_columns] = dark
    return grey


def rough_rock():
    obj = ico_sphere("RoughRock", 6)
    displace(obj, "VORONOI", 0.35, noise_scale=0.35, distance_metric="DISTANCE")
    displace(obj, "CLOUDS", 0.06, noise_scale=0.05, noise_depth=4)
    for vertex in obj.data.vertices:
        if vertex.co.x > 0.1 and vertex.co.z > -0.1:
            vertex.co.x -= 0.6 * (vertex.co.x - 0.1) * min(1.0, (vertex.co.z + 0.1) / 0.3)
    scaled(obj, (1.0, 0.8, 0.65))
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    textured(obj, packed_image("rock-albedo", 0.25 + 0.6 * value_noise(256, 7)))
    return obj


def leaf_cloud(count=1500):
    rng = random.Random(21)
    bm = bmesh.new()
    for _ in range(count):
        centre = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
        centre = centre.normalized() * (rng.random() ** 0.35) * 0.5
        size = 0.02 + 0.03 * rng.random()
        axis = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized()
        side = axis.orthogonal().normalized()
        third = axis.cross(side)
        points = [centre + side * size, centre + third * size * 0.4 - side * size * 0.3, centre - third * size * 0.4 - side * size * 0.3]
        bm.faces.new([bm.verts.new(point) for point in points])
    return mesh_object("LeafCloud", bm)


def build(folder, name, make):
    reset()
    make()
    export_glb(folder, name)


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    build(folder, "uv-sphere", lambda: textured(uv_sphere(), packed_image("sphere-colour", np.full((64, 64), 0.5))))
    build(folder, "clouds-ico", clouds_ico)
    build(folder, "jittered-ico", jittered_ico)
    build(folder, "cylinder-tree", cylinder_tree)
    build(folder, "cube", cube)
    build(folder, "rough-rock", rough_rock)
    build(folder, "leaf-cloud", leaf_cloud)
    build(folder, "card-opaque", lambda: upright_card(False))
    build(folder, "card-cutout", lambda: upright_card(True))
    build(folder, "albedo-flat", lambda: textured(unit_plane(), packed_image("flat", np.full((64, 64), 0.4))))
    build(folder, "albedo-two-tone", lambda: textured(unit_plane(), packed_image("two-tone", two_tone())))


main()
