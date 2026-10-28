import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

PROPERTY = "blendworks_skeleton"
RING = 64
COPIES = 100
SIZES = 300
TREES = 150
FOREST_RING = 12


def arguments():
    return sys.argv[sys.argv.index("--") + 1 :][0]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def export_glb(folder, name):
    bpy.ops.export_scene.gltf(filepath=os.path.join(folder, f"{name}.glb"), export_format="GLB", export_extras=True)


def mesh_object(name, bm):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def value_noise(size, seed, cells=8, octaves=5):
    rng = np.random.default_rng(seed)
    field = np.zeros((size, size))
    amplitude = 1.0
    for octave in range(octaves):
        count = cells * 2**octave
        lattice = rng.random((count + 1, count + 1))
        position = np.arange(size) * count / size
        index = position.astype(int)
        fraction = position - index
        smooth = fraction * fraction * (3 - 2 * fraction)
        rows = lattice[index] * (1 - smooth)[:, None] + lattice[index + 1] * smooth[:, None]
        field += amplitude * (rows[:, index] * (1 - smooth)[None, :] + rows[:, index + 1] * smooth[None, :])
        amplitude *= 0.6
    field -= field.min()
    return field / field.max()


def textured_plane(name, grey):
    bm = bmesh.new()
    layer = bm.loops.layers.uv.new("UVMap")
    corners = [bm.verts.new(point) for point in ((-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0))]
    face = bm.faces.new(corners)
    for loop, uv in zip(face.loops, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        loop[layer].uv = uv
    obj = mesh_object(name, bm)
    height, width = grey.shape
    image = bpy.data.images.new(f"{name}-colour", width, height)
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = (0.15 + 0.7 * grey)[:, :, None]
    image.pixels.foreach_set(rgba.ravel())
    image.pack()
    material = bpy.data.materials.new(f"{name}-material")
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    material.node_tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = 1.0
    obj.data.materials.append(material)
    return obj


def tiled_plane():
    textured_plane("TiledPlane", np.tile(value_noise(128, 3, cells=4), (4, 4)))


def untiled_plane():
    textured_plane("UntiledPlane", value_noise(512, 4, cells=16))


def pebble_mesh():
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    rng = np.random.default_rng(8)
    for vertex in bm.verts:
        vertex.co = Vector((vertex.co.x * 1.4, vertex.co.y, vertex.co.z * 0.7)) * (1.0 + 0.15 * rng.uniform(-1.0, 1.0))
    mesh = bpy.data.meshes.new("Pebble")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def copies(varied, realized):
    mesh = pebble_mesh()
    rng = np.random.default_rng(13)
    placed = []
    for index in range(COPIES):
        obj = bpy.data.objects.new(f"Pebble.{index:03d}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = (3.0 * (index % 10), 3.0 * (index // 10), 0.0)
        if varied:
            obj.scale = (float(rng.uniform(0.5, 1.5)),) * 3
            obj.rotation_euler = (0.0, 0.0, float(rng.uniform(0.0, 2.0 * math.pi)))
        placed.append(obj)
    if realized:
        for obj in placed:
            obj.data = obj.data.copy()
        bpy.ops.object.select_all(action="DESELECT")
        for obj in placed:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = placed[0]
        bpy.ops.object.join()


def power_sizes(rng, count, low, high, exponent):
    shift = exponent + 1.0
    return (low**shift + rng.random(count) * (high**shift - low**shift)) ** (1.0 / shift)


def size_set(diameters):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    mesh = bpy.data.meshes.new("Stone")
    bm.to_mesh(mesh)
    bm.free()
    columns = int(math.ceil(math.sqrt(len(diameters))))
    for index, diameter in enumerate(diameters.tolist()):
        obj = bpy.data.objects.new(f"Stone.{index:03d}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = (2.5 * (index % columns), 2.5 * (index // columns), diameter / 2.0)
        obj.scale = (diameter,) * 3


class TreeBuilder:
    def __init__(self, delta, seed, base_radius=0.1, step=0.25, plan=(4, 3, 2)):
        self.delta = delta
        self.rng = np.random.default_rng(seed)
        self.step = step
        self.plan = plan
        self.positions = [Vector((0.0, 0.0, 0.0))]
        self.parents = [-1]
        self.radii = [base_radius]
        self.orders = [0]
        self.axes = []
        self.grow(0, Vector((0.0, 0.0, 1.0)), base_radius, 0, 12)

    def add(self, position, parent, radius, order):
        self.positions.append(position)
        self.parents.append(parent)
        self.radii.append(radius)
        self.orders.append(order)
        return len(self.positions) - 1

    def grow(self, start, direction, radius, order, length):
        sides = self.plan[order] if order < len(self.plan) else 0
        branch_at = {2 + 2 * index for index in range(sides)}
        chain = [start]
        current = start
        for segment in range(1, length + 1):
            node = self.add(self.positions[current] + direction * self.step, current, radius, order)
            chain.append(node)
            current = node
            if segment in branch_at and segment < length:
                share = float(self.rng.uniform(0.2, 0.5))
                side_radius = radius * share ** (1.0 / self.delta)
                radius = radius * (1.0 - share) ** (1.0 / self.delta)
                turn = float(self.rng.uniform(0.0, 2.0 * math.pi))
                tilt = math.radians(float(self.rng.uniform(40.0, 55.0)))
                helper = Vector((1.0, 0.0, 0.0)) if abs(direction.x) < 0.9 else Vector((0.0, 1.0, 0.0))
                first = direction.cross(helper).normalized()
                second = direction.cross(first)
                side = (direction * math.cos(tilt) + (first * math.cos(turn) + second * math.sin(turn)) * math.sin(tilt)).normalized()
                self.grow(node, side, side_radius, order + 1, max(4, length // 2))
        self.axes.append(chain)

    def skeleton(self, version=1):
        count = len(self.positions)
        return {
            "format": "blendworks.skeleton",
            "version": version,
            "units": "metre",
            "space": "object",
            "up": "z",
            "method": "levels",
            "exponent": float(self.delta),
            "tip_radius": float(min(self.radii)),
            "count": count,
            "position": [float(value) for point in self.positions for value in point],
            "parent": self.parents,
            "radius": [float(value) for value in self.radii],
            "order": self.orders,
            "kind": [0] * count,
        }


def ring(bm, centre, direction, radius, segments):
    helper = Vector((1.0, 0.0, 0.0)) if abs(direction.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    first = direction.cross(helper).normalized()
    second = direction.cross(first)
    return [bm.verts.new(centre + (first * math.cos(2.0 * math.pi * k / segments) + second * math.sin(2.0 * math.pi * k / segments)) * radius) for k in range(segments)]


def tube_mesh(builder, radius_of, segments=RING, bm=None):
    bm = bmesh.new() if bm is None else bm
    for chain in builder.axes:
        direction = (builder.positions[chain[-1]] - builder.positions[chain[0]]).normalized()
        rings = [ring(bm, builder.positions[node], direction, radius_of(chain[1] if index == 0 else node), segments) for index, node in enumerate(chain)]
        for low, high in zip(rings, rings[1:]):
            for k in range(segments):
                bm.faces.new((low[k], low[(k + 1) % segments], high[(k + 1) % segments], high[k]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def tree(name, delta, seed=5, equal=False, skeleton=True, version=1):
    builder = TreeBuilder(delta, seed)
    obj = mesh_object(name, tube_mesh(builder, (lambda node: 0.04) if equal else (lambda node: builder.radii[node])))
    if skeleton:
        obj[PROPERTY] = builder.skeleton(version)
    return obj


def shifted(builder, offset):
    builder.positions = [point + offset for point in builder.positions]
    return builder


def forged(spanning):
    plain = TreeBuilder(2.0, 5)
    spot = shifted(TreeBuilder(2.0, 7, base_radius=0.05, step=0.1, plan=(2,)), Vector((2.0, 0.0, 0.0)))
    bm = tube_mesh(plain, lambda node: 0.04, bm=None)
    tube_mesh(spot, lambda node: spot.radii[node], bm=bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = mesh_object("Tree", bm)
    skeleton = spot.skeleton()
    if spanning:
        trunk = [plain.positions[node] for node in plain.axes[-1]]
        count = skeleton["count"]
        skeleton["position"] += [float(value) for point in trunk for value in point]
        skeleton["parent"] += [0] + list(range(count, count + len(trunk) - 1))
        skeleton["radius"] += [0.04] * len(trunk)
        skeleton["order"] += [1] * len(trunk)
        skeleton["kind"] += [0] * len(trunk)
        skeleton["count"] = count + len(trunk)
    obj[PROPERTY] = skeleton


def outside():
    builder = TreeBuilder(2.0, 5)
    obj = mesh_object("Tree", tube_mesh(builder, lambda node: builder.radii[node]))
    obj[PROPERTY] = shifted(builder, Vector((10.0, 0.0, 0.0))).skeleton()


def malformed(change):
    builder = TreeBuilder(2.0, 5)
    obj = mesh_object("Tree", tube_mesh(builder, lambda node: builder.radii[node]))
    skeleton = builder.skeleton()
    change(skeleton)
    obj[PROPERTY] = skeleton


def sparse():
    builder = TreeBuilder(2.0, 5, plan=(1,))
    obj = mesh_object("Tree", tube_mesh(builder, lambda node: builder.radii[node]))
    obj[PROPERTY] = builder.skeleton()


def forest():
    builder = TreeBuilder(2.0, 9, base_radius=0.1, plan=(2,))
    template = mesh_object("Tree", tube_mesh(builder, lambda node: builder.radii[node], FOREST_RING))
    template[PROPERTY] = builder.skeleton()
    rng = np.random.default_rng(17)
    scales = power_sizes(rng, TREES, 0.5, 4.0, -2.0)
    columns = int(math.ceil(math.sqrt(TREES)))
    for index, scale in enumerate(scales.tolist()):
        obj = template if index == 0 else template.copy()
        if index > 0:
            bpy.context.scene.collection.objects.link(obj)
        obj.name = f"Tree.{index:03d}"
        obj.location = (8.0 * (index % columns), 8.0 * (index // columns), 0.0)
        obj.scale = (scale,) * 3


def build(folder, name, make):
    reset()
    make()
    export_glb(folder, name)


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    build(folder, "tiled-plane", tiled_plane)
    build(folder, "untiled-plane", untiled_plane)
    build(folder, "copies-identical", lambda: copies(False, False))
    build(folder, "copies-varied", lambda: copies(True, False))
    build(folder, "copies-realized", lambda: copies(False, True))
    build(folder, "copies-realized-varied", lambda: copies(True, True))
    build(folder, "sizes-power", lambda: size_set(power_sizes(np.random.default_rng(21), SIZES, 0.1, 1.0, -2.0)))
    build(folder, "sizes-uniform", lambda: size_set(np.random.default_rng(22).uniform(0.1, 1.0, SIZES)))
    build(folder, "leonardo-2", lambda: tree("Tree", 2.0))
    build(folder, "leonardo-3", lambda: tree("Tree", 3.0))
    build(folder, "leonardo-equal", lambda: tree("Tree", 2.0, equal=True))
    build(folder, "leonardo-none", lambda: tree("Tree", 2.0, skeleton=False))
    build(folder, "leonardo-v2", lambda: tree("Tree", 2.0, version=2))
    build(folder, "forest", forest)
    build(folder, "leonardo-forged", lambda: forged(False))
    build(folder, "leonardo-forged-spanning", lambda: forged(True))
    build(folder, "leonardo-outside", outside)
    build(folder, "leonardo-toomany", lambda: malformed(lambda skeleton: skeleton.update(count=50001)))
    build(folder, "leonardo-sparse", sparse)
    build(folder, "leonardo-format", lambda: malformed(lambda skeleton: skeleton.update(format="blendworks.skeleton.v1")))


main()
