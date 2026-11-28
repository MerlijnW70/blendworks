"""Near-camera micro-relief of formed ground: centimetre relief displaced by Cycles adaptive subdivision, bump beyond.

Formed terrain (ground_form.TERRAIN_FLAG) carries ground_relief, the standard deviation in metres of its micro-relief by
surface class (ground_form.ROUGHNESS). For the render, render_final gives its materials a displacement of that size: a
fractal field of clods, grains and roots from FEATURE down to a centimetre, scaled so its standard deviation is one
(SPREAD: the field's measured deviation is 0.0624), times ground_relief. Within NEAR metres of the camera it displaces
the surface and fades to none at FAR, beyond which it only bends the normal: 2 cm of relief spans 0.7 px of a 1920 px
frame through a 35 mm lens at 18 m and a quarter pixel at 50 m. The adaptive subdivision dices patches to about a pixel
within GROUND_BUDGET triangles, with the same estimate as rock_relief (covered pixels, plus a floor of two triangles per
quad patch); a ground mesh whose patch floor alone passes half the budget keeps only the bump. The materials and
modifiers are restored after the render.
"""
import bpy
import numpy

from . import ground_form, rock_relief
from .nodes import Graph

NEAR = 15.0
FAR = 45.0
FEATURE = 0.08
SPREAD = 16.0
GROUND_BUDGET = 6_000_000
PREFIX = "bw_ground_"
DEPTH_ATTRIBUTE = "liquid_depth"
WET_BAND = 0.12
MODIFIER = "Blendworks Ground Detail"


def terrain_objects(scene):
    return [obj for obj in scene.objects if obj.type == "MESH" and not obj.hide_render and obj.get(ground_form.TERRAIN_FLAG)
            and ground_form.RELIEF_ATTRIBUTE in obj.data.attributes]


def patch_floor(mesh):
    """Least triangles Cycles dices a mesh into: two per patch, one patch per quad and one per corner of other faces."""
    sides = numpy.zeros(len(mesh.polygons), dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_total", sides)
    return 2.0 * float(numpy.where(sides == 4, 1, sides).sum())


def covered(obj, depsgraph, frame):
    view, focal, half_width, half_height = frame
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        points = numpy.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", points)
        triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("vertices", triangles)
        floor = patch_floor(mesh)
    finally:
        evaluated.to_mesh_clear()
    if not len(triangles):
        return 0.0, 0.0
    world = numpy.array(obj.matrix_world, dtype=numpy.float64)
    eye = (points.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]) @ view[:3, :3].T + view[:3, 3]
    corners = eye[triangles.reshape(-1, 3)]
    distance = numpy.linalg.norm(corners, axis=2).min(axis=1)
    corners = rock_relief.fine_enough(corners[distance < FAR + numpy.linalg.norm(corners[:, 0] - corners[:, 1], axis=1)])
    centre = corners.mean(axis=1)
    depth = numpy.maximum(-centre[:, 2], 1e-3)
    area = 0.5 * numpy.linalg.norm(numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    pixels = area * (focal / depth) ** 2
    seen = (-centre[:, 2] > 0.0) & (numpy.abs(centre[:, 0] / depth * focal) <= half_width) & (numpy.abs(centre[:, 1] / depth * focal) <= half_height)
    return rock_relief.capped(pixels, seen, numpy.linalg.norm(centre, axis=1) < FAR, half_width, half_height), floor


def relief_height(graph, near):
    """The micro-relief in metres and its near and far parts: ground_relief times a unit-deviation fractal field. Ground
    under water or within WET_BAND above it (liquid_depth, which every water body writes on its ground) is fine sediment,
    the mud class, whatever it was classed dry: a sward's relief would stand through shallow water."""
    amplitude = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=ground_form.RELIEF_ATTRIBUTE).outputs["Fac"]
    depth = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=DEPTH_ATTRIBUTE).outputs["Fac"]
    wet = graph.math("GREATER_THAN", depth, -WET_BAND)
    measured = graph.math("GREATER_THAN", graph.math("ABSOLUTE", depth), 1e-6)
    amplitude = graph.mix(graph.math("MULTIPLY", wet, measured), amplitude, ground_form.ROUGHNESS["mud"], "FLOAT")
    position = graph.node("ShaderNodeNewGeometry").outputs["Position"]
    field = graph.noise(position, 1.0 / FEATURE, detail=6.0, roughness=0.62).outputs["Factor"]
    metres = graph.math("MULTIPLY", graph.math("MULTIPLY", graph.math("SUBTRACT", field, 0.5), SPREAD), amplitude)
    return graph.math("MULTIPLY", metres, near), graph.math("MULTIPLY", metres, graph.math("SUBTRACT", 1.0, near))


class Injected:
    """The relief nodes added to one material, and how to take them out again."""

    def __init__(self, material):
        self.material = material
        self.method = material.displacement_method
        tree = material.node_tree
        self.before = set(node.name for node in tree.nodes)
        output = next((node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
        shader = next((node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        self.links = []
        if output is None:
            return
        graph = Graph(tree)
        near = graph.map_range(graph.node("ShaderNodeCameraData").outputs["View Distance"], NEAR, FAR, 1.0, 0.0, "SMOOTHSTEP")
        displaced, bumped = relief_height(graph, near)
        vector = graph.node("ShaderNodeDisplacement", {"Height": displaced, "Midlevel": 0.0, "Scale": 1.0}, space="WORLD").outputs["Displacement"]
        socket = output.inputs["Displacement"]
        old = socket.links[0].from_socket if socket.is_linked else None
        if old is not None:
            self.links.append((old, socket))
            vector = graph.vector_math("ADD", vector, old)
        graph.set(socket, vector)
        if shader is not None:
            normal = shader.inputs["Normal"]
            previous = normal.links[0].from_socket if normal.is_linked else None
            bump = graph.node("ShaderNodeBump", {"Height": bumped, "Distance": 1.0, "Strength": 1.0, "Normal": previous})
            if previous is not None:
                self.links.append((previous, normal))
            graph.set(normal, bump.outputs["Normal"])
        material.displacement_method = "BOTH"
        for node in tree.nodes:
            if node.name not in self.before:
                node.name = PREFIX + node.name

    def remove(self):
        tree = self.material.node_tree
        for node in [node for node in tree.nodes if node.name not in self.before]:
            tree.nodes.remove(node)
        for source, target in self.links:
            tree.links.new(source, target)
        self.material.displacement_method = self.method


class RenderDetail:
    """For a shaded render: the relief nodes in the materials of formed ground, and an adaptive simple subdivision on the
    ground meshes that come within FAR of the camera, nearest first while their patch floors fit in half of GROUND_BUDGET."""

    def __init__(self, scene, camera, active=True):
        self.scene, self.camera, self.active = scene, camera, active
        self.injected, self.added = [], []
        self.report = {"ground_detail": None}

    def __enter__(self):
        objects = terrain_objects(self.scene) if self.active else []
        if not objects:
            return self
        depsgraph = bpy.context.evaluated_depsgraph_get()
        frame = rock_relief.camera_frame(self.scene, self.camera)
        measures = {obj.name: covered(obj, depsgraph, frame) for obj in objects}
        picked, floor = [], 0.0
        for obj in objects:
            pixels, least = measures[obj.name]
            if pixels > 0.0 and floor + least <= 0.5 * GROUND_BUDGET:
                picked.append(obj)
                floor += least
        size, estimate = rock_relief.dicing_for(sum(measures[obj.name][0] for obj in picked), GROUND_BUDGET, floor)
        materials = {slot.material.name: slot.material for obj in objects for slot in obj.material_slots if slot.material is not None and slot.material.node_tree is not None}
        self.injected = [Injected(material) for material in materials.values()]
        for obj in picked:
            if obj.modifiers and obj.modifiers[-1].type == "SUBSURF" and obj.modifiers[-1].use_adaptive_subdivision:
                continue
            modifier = obj.modifiers.new(MODIFIER, "SUBSURF")
            modifier.subdivision_type = "SIMPLE"
            modifier.levels = modifier.render_levels = 0
            modifier.use_adaptive_subdivision = True
            modifier.adaptive_space = "PIXEL"
            modifier.adaptive_pixel_size = size
            self.added.append((obj.name, modifier.name))
        self.report = {"ground_detail": {"objects": len(picked), "bump_only": len(objects) - len(picked), "pixel_size": round(size, 4),
                                         "estimated_triangles": int(round(estimate)), "budget": GROUND_BUDGET, "near": NEAR, "far": FAR}}
        return self

    def __exit__(self, kind, error, trace):
        for name, modifier in self.added:
            obj = bpy.data.objects.get(name)
            if obj is not None and modifier in obj.modifiers:
                obj.modifiers.remove(obj.modifiers[modifier])
        for injected in self.injected:
            injected.remove()
        self.added, self.injected = [], []
        return False
