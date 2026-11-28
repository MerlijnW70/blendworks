"""Surface relief of rock: true displacement near the camera, bump beyond, within a triangle budget.

The relief height (grains, pits, cracks, fracture faces, lichen and moss) is in metres: the preset's height times its
bump depth in millimetres. Within NEAR metres of the camera it displaces the surface (Cycles adaptive subdivision dices
each patch to about DICING_PIXELS pixels at render time), and fades to none at FAR, beyond which the same height only
bends the normal (bump). NEAR and FAR follow from the pixel footprint of a 1920 px frame through a 35 mm lens on a 36 mm
sensor, 0.54 mm per metre of distance: 2 mm of relief spans about 0.7 px at 5 m and 0.25 px at 15 m, where displacing it
no longer changes what a pixel sees. A render dices at most TRIANGLE_BUDGET triangles of rock: a patch diced to p pixels
gives 2 / p^2 triangles per pixel it covers, so render_final estimates the covered pixels and coarsens p until the
estimate fits; a mesh too finely divided to dice within half the budget, nearest first, keeps only the bump. Cycles
keeps about MEMORY_PER_TRIANGLE bytes per diced triangle (measured), so the budget is about 1 GB.
"""
import json

import bpy
import numpy

ROCK_FLAG = "blendworks_rock"
NEAR = 5.0
FAR = 15.0
DICING_PIXELS = 1.0
TRIANGLE_BUDGET = 6_000_000
MEMORY_PER_TRIANGLE = 180
OFFSCREEN_SCALE = 4.0
OVERDRAW = 3.0
AROUND = 6.0
MODIFIER = "Blendworks Rock Detail"
HEADROOM = 8.0
PATCHES_PER_TRIANGLE = 3
SPLIT_SHARE = 0.25
SPLIT_ROUNDS = 8
MAX_ESTIMATE_TRIANGLES = 4_000_000


def near_share(graph):
    distance = graph.node("ShaderNodeCameraData").outputs["View Distance"]
    return graph.map_range(distance, NEAR, FAR, 1.0, 0.0, "SMOOTHSTEP")


def finish(graph, p, layers):
    """The channels of the rock preset: colour, roughness, the relief as true displacement near the camera and as bump
    elsewhere, a fully rough diffuse lobe (dry rock scatters like a rough Oren-Nayar surface, not like plastic), and the
    weathering masks as AOVs that tests and compositing can read."""
    metres = graph.math("MULTIPLY", layers["height"], p["bump"] / 1000.0)
    near = near_share(graph)
    displaced = graph.math("MULTIPLY", metres, near)
    displacement = graph.node("ShaderNodeDisplacement", {"Height": displaced, "Midlevel": 0.0, "Scale": 1.0}, space="WORLD").outputs["Displacement"]
    bumped = graph.math("MULTIPLY", metres, graph.math("SUBTRACT", 1.0, near))
    normal = graph.node("ShaderNodeBump", {"Height": bumped, "Distance": 1.0, "Strength": 1.0}).outputs["Normal"]
    return {
        "base_color": layers["color"],
        "roughness": layers["roughness"],
        "metallic": 0.0,
        "height": layers["height"],
        "normal": normal,
        "diffuse_roughness": 1.0,
        "displacement": displacement,
        "displacement_method": "BOTH",
        "max_displacement": HEADROOM * p["bump"] / 1000.0,
        "flag": (ROCK_FLAG, json.dumps(p, sort_keys=True)),
        "aov": {"rock_lichen": layers["lichen"], "rock_moss": layers["moss"], "rock_algae": layers["algae"], "rock_mark": layers["mark"], "rock_relief": displaced},
    }


def is_rock_material(material):
    return material is not None and material.get(ROCK_FLAG) is not None


def rock_objects(scene):
    found = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        if any(is_rock_material(slot.material) for slot in obj.material_slots):
            found.append(obj)
    return found


def camera_frame(scene, camera):
    """World-to-camera matrix, focal length in pixels and the frame's half sizes in pixels."""
    render = scene.render
    width, height = render.resolution_x * render.resolution_percentage / 100.0, render.resolution_y * render.resolution_percentage / 100.0
    data = camera.data
    if data.sensor_fit == "VERTICAL":
        focal = data.lens / data.sensor_height * height
    elif data.sensor_fit == "HORIZONTAL":
        focal = data.lens / data.sensor_width * width
    else:
        focal = data.lens / data.sensor_width * max(width, height)
    return numpy.array(camera.matrix_world.inverted(), dtype=numpy.float64), focal, 0.5 * width, 0.5 * height


def covered_pixels(obj, depsgraph, frame):
    """Pixels the object's triangles within FAR of the camera would cover if they faced it (an upper bound), counting those
    outside the frame at the offscreen dicing scale; the least diced triangles of the object (Cycles makes every triangle
    PATCHES_PER_TRIANGLE quad patches of at least two triangles each, however small or far); and its distance from the
    camera."""
    view, focal, half_width, half_height = frame
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        count = len(mesh.vertices)
        points = numpy.empty(count * 3)
        mesh.vertices.foreach_get("co", points)
        triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("vertices", triangles)
    finally:
        evaluated.to_mesh_clear()
    if not len(triangles):
        return 0.0, 0.0, numpy.inf
    least = 2.0 * PATCHES_PER_TRIANGLE * len(triangles) // 3
    world = numpy.array(obj.matrix_world, dtype=numpy.float64)
    local = points.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
    eye = local @ view[:3, :3].T + view[:3, 3]
    corners = fine_enough(eye[triangles.reshape(-1, 3)])
    centre = corners.mean(axis=1)
    distance = numpy.linalg.norm(centre, axis=1)
    depth = numpy.maximum(-centre[:, 2], 1e-3)
    area = 0.5 * numpy.linalg.norm(numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    pixels = area * (focal / depth) ** 2
    seen = (-centre[:, 2] > 0.0) & (numpy.abs(centre[:, 0] / depth * focal) <= half_width) & (numpy.abs(centre[:, 1] / depth * focal) <= half_height)
    return capped(pixels, seen, distance < FAR, half_width, half_height), float(least), float(distance.min())


def capped(pixels, seen, counted, half_width, half_height):
    """Covered pixels of triangles within reach: no triangle covers more than the frame (one at the camera would count
    millions), the visible ones together at most OVERDRAW frames (surfaces seen behind one another), the hidden ones at the
    offscreen dicing scale, together at most AROUND frames (the whole sphere around the camera)."""
    frame = 4.0 * half_width * half_height
    pixels = numpy.minimum(pixels, frame)
    visible = min(float(pixels[seen & counted].sum()), OVERDRAW * frame)
    hidden = min(float(pixels[~seen & counted].sum()), AROUND * frame)
    return visible + hidden / OFFSCREEN_SCALE**2


def fine_enough(corners):
    """Triangles (n, 3, 3) split into four until each is small against its distance from the camera (its longest edge at
    most SPLIT_SHARE of it) or SPLIT_ROUNDS have passed, so a big triangle that reaches from near to far counts its near part."""
    for _ in range(SPLIT_ROUNDS):
        edges = numpy.linalg.norm(corners - numpy.roll(corners, 1, axis=1), axis=2).max(axis=1)
        coarse = edges > SPLIT_SHARE * numpy.linalg.norm(corners.mean(axis=1), axis=1)
        if not coarse.any() or len(corners) + 3 * int(coarse.sum()) > MAX_ESTIMATE_TRIANGLES:
            break
        big = corners[coarse]
        a, b, c = big[:, 0], big[:, 1], big[:, 2]
        ab, bc, ca = 0.5 * (a + b), 0.5 * (b + c), 0.5 * (c + a)
        pieces = numpy.concatenate([numpy.stack(group, axis=1) for group in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])
        corners = numpy.concatenate([corners[~coarse], pieces])
    return corners


def dicing_for(pixels, budget=None, least=0.0):
    """The dicing size in pixels that keeps least + 2 * pixels / size^2 triangles within the budget (TRIANGLE_BUDGET by
    default), and that estimate; least is the floor of the patches themselves."""
    budget = TRIANGLE_BUDGET if budget is None else budget
    size = DICING_PIXELS
    room = max(budget - least, 1.0)
    if 2.0 * pixels / size**2 > room:
        size = float(numpy.sqrt(2.0 * pixels / room))
    return size, least + 2.0 * pixels / size**2


def chosen(measures, budget=None):
    """The objects to dice, nearest first, while their patch floors fit in half the budget: a mesh of many small triangles
    (a realised scatter of thousands of stones) would cost more than the budget before any detail, so it keeps the bump."""
    budget = TRIANGLE_BUDGET if budget is None else budget
    picked, floor = [], 0.0
    for name, (pixels, least, distance) in sorted(measures.items(), key=lambda item: (item[1][2], item[0])):
        if pixels > 0.0 and floor + least <= 0.5 * budget:
            picked.append(name)
            floor += least
    return picked, floor


class RenderDetail:
    """Adds an adaptive simple subdivision as the last modifier of every rendered mesh that uses a rock material and comes
    within FAR of the camera, at a dicing size that keeps the scene within TRIANGLE_BUDGET; removes it again afterwards."""

    def __init__(self, scene, view_layer, camera, active=True):
        self.scene, self.view_layer, self.camera, self.active = scene, view_layer, camera, active
        self.added = []
        self.report = {"rock_detail": None}

    def __enter__(self):
        if not self.active:
            return self
        objects = [obj for obj in rock_objects(self.scene) if not adaptive_already(obj)]
        if not objects:
            return self
        depsgraph = bpy.context.evaluated_depsgraph_get()
        frame = camera_frame(self.scene, self.camera)
        measures = {obj.name: covered_pixels(obj, depsgraph, frame) for obj in objects}
        names, floor = chosen(measures)
        near = [obj for obj in objects if obj.name in names]
        size, estimate = dicing_for(sum(measures[name][0] for name in names), least=floor)
        for obj in near:
            modifier = obj.modifiers.new(MODIFIER, "SUBSURF")
            modifier.subdivision_type = "SIMPLE"
            modifier.levels = 0
            modifier.render_levels = 0
            modifier.use_adaptive_subdivision = True
            modifier.adaptive_space = "PIXEL"
            modifier.adaptive_pixel_size = size
            self.added.append((obj.name, modifier.name))
        self.scene.cycles.offscreen_dicing_scale = OFFSCREEN_SCALE
        self.report = {"rock_detail": {"objects": len(near), "bump_only": len(objects) - len(near), "pixel_size": round(size, 4),
                                       "estimated_triangles": int(round(estimate)), "budget": TRIANGLE_BUDGET, "near": NEAR, "far": FAR}}
        return self

    def __exit__(self, kind, error, trace):
        for name, modifier in self.added:
            obj = bpy.data.objects.get(name)
            if obj is not None and modifier in obj.modifiers:
                obj.modifiers.remove(obj.modifiers[modifier])
        self.added = []
        return False


def adaptive_already(obj):
    return bool(obj.modifiers) and obj.modifiers[-1].type == "SUBSURF" and obj.modifiers[-1].use_adaptive_subdivision
