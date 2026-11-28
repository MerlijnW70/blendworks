"""The distant_forest command: forest on distant land from the tree species, as grown variants, cards and canopy."""

import json
import math

import bpy
import numpy
from mathutils import Matrix, Vector

from .. import forest_cards, forest_grove, forest_inplace, forest_place, impostors
from ..forest_canopy import LIFT_ATTRIBUTE, canopy_surface
from ..camera_reach import raise_all
from ..cover_nodes import points_object
from ..errors import bad_args
from ..land_material import WATER_ATTRIBUTE
from ..limits import FRACTION, MAX_COORDINATE, MAX_SEED, QUARTER_TURN
from ..limits_land import (LEAST_IMPOSTOR_PIXELS, MAX_FOREST_BAND, MAX_FOREST_TREES, MAX_FOREST_VARIANTS, MAX_IMPOSTOR_FRAMES,
                           MAX_IMPOSTOR_PIXELS, MAX_PROTOCOL_SPECIES)
from ..registry import COMMANDS, command
from ..schema import CREATES, EXISTS, array, boolean, integer, length, names, number, ref, string, validate
from ..tree_presets import SPECIES as TREE_PRESETS
from ..tree_species import SPECIES_NAMES
from ..util import get_object, require_free_name, rounded
from .distant_land import PROPERTY

DEFAULT_NAME = "DistantForest"
TRANSPARENT_BOUNCES = 256
GROWN_POINTS = 6000
LEAST_POINTS = 200
EMBED = 0.15


class Placed:
    def __init__(self, positions, pick, key, matrices):
        self.positions, self.pick, self.key, self.matrices = positions, pick, key, matrices
        self.card = numpy.zeros(len(pick), dtype=numpy.int32)
        self.tint = numpy.zeros(len(pick))

    def __len__(self):
        return len(self.pick)


def plan_forest(args, state):
    for suffix in ("", "_near", "_cards", "_shadows"):
        state.add("object", args["name"] + suffix)
    state.add("material", args["name"] + "_impostor")


@command(
    "distant_forest",
    "Forest on distant land from Blendworks' own tree species: real trees near the camera, baked impostor cards farther out, a canopy surface beyond.",
    {
        "name": ref(string("Name of the forest's group; its parts get suffixes.", default=DEFAULT_NAME), "object", CREATES),
        "land": ref(string("The distant_land object the forest grows on."), "object", EXISTS),
        "species": array({"type": "string", "enum": list(SPECIES_NAMES)}, "Tree species to grow, each a variant or more.", 1, MAX_PROTOCOL_SPECIES, ["pine", "oak", "birch"]),
        "variants": integer("Trees grown per species.", 1, MAX_FOREST_VARIANTS, 1),
        "sources": ref(names("Existing tree meshes (trunk base at the origin, leaves joined) to use instead of growing species.", max_items=MAX_FOREST_VARIANTS), "object"),
        "tree_detail": number("Share of a full tree's attraction points the grown trees use; distant trees need few.", None, FRACTION, 0.25, exclusive_minimum=0.0),
        "cover": number("Share of the dry land the forest covers, as far as the rules allow.", 0.0, FRACTION, 0.4),
        "max_slope": number("Steepest ground in degrees that carries forest.", 0.0, QUARTER_TURN, 32.0),
        "height_range": array({"type": "number", "minimum": -MAX_COORDINATE, "maximum": MAX_COORDINATE}, "Lowest and highest ground height in metres that carries forest.", 2, 2),
        "water_margin": length("Metres of open shore kept between water and forest.", 25.0),
        "patch_size": length("Wavelength in metres of the patches of forest and open land.", 1500.0),
        "spacing": length("Distance between trees in metres. Default: from the crown width."),
        "camera": ref(string("Camera the forest is built for. Default: the active camera."), "object", EXISTS),
        "near": length("Trees closer than this many metres to the camera are real trees.", 250.0),
        "far": length("Trees out to this many metres are impostor cards; beyond, the canopy surface.", 3000.0),
        "band": number("Share of each switch distance over which trees dither from one form to the next.", 0.0, MAX_FOREST_BAND, 0.2),
        "frames": integer("Impostor views per side of the hemi-octahedral atlas.", 1, MAX_IMPOSTOR_FRAMES, 8),
        "frame_pixels": integer("Pixels per side of each impostor view.", LEAST_IMPOSTOR_PIXELS, MAX_IMPOSTOR_PIXELS, 96),
        "view_only": boolean("Place real trees and cards only where the camera looks.", True),
        "budget": integer("Most real trees and cards together; the card reach shrinks to fit.", 1, MAX_FOREST_TREES, 120_000),
        "canopy_height": length("Height of the canopy surface over the ground. Default: 0.85 of the trees' height."),
        "seed": integer("Random seed of trees and patches.", 0, MAX_SEED, 0),
    },
    ["land"],
    plan=plan_forest,
    slow=True,
    family="shapes",
    intents=("forest in the distance", "forested hills to the horizon", "tree impostors for far trees"),
    nearest=(("grow_tree", "for single trees near the camera"), ("distant_land", "for the land the forest grows on")),
)
def distant_forest(ctx, args):
    name = args["name"]
    for suffix in ("", "_near", "_cards", "_shadows"):
        require_free_name(name + suffix)
    land = get_object(args["land"])
    if land.type != "MESH" or not isinstance(land.get(PROPERTY), str):
        raise bad_args(f"{land.name} is not distant land; make it with distant_land")
    camera = get_object(args["camera"]) if "camera" in args else ctx.scene.camera
    if camera is None or camera.type != "CAMERA":
        raise bad_args("the forest is built for a camera: give camera or add one")
    if args["near"] >= args["far"]:
        raise bad_args("near must be below far")
    trees_collection = hidden_collection(ctx, name + "_trees")
    variants = grown_variants(ctx, args, trees_collection) if "sources" not in args else copied_sources(args, trees_collection)
    spheres = [impostors.bounds_sphere([obj]) for obj in variants]
    bake_collections = []
    for index, obj in enumerate(variants):
        collection = bpy.data.collections.new(f"{name}_bake_{index:02d}")
        collection.objects.link(obj)
        bake_collections.append(collection)
    atlases = [impostors.Bake(collection, args["frames"], args["frame_pixels"], centre, radius).render()
               for collection, (centre, radius, _) in zip(bake_collections, spheres)]
    colour_image, normal_image = impostors.atlas_images(name, atlases)
    for image in (colour_image, normal_image):
        image.alpha_mode = "CHANNEL_PACKED"
    material = forest_cards.impostor_material(name + "_impostor", colour_image, normal_image, (1.0, 1.0, 1.0))
    tree, points, faces = forest_place.land_tree(land)
    eye = numpy.array(camera.matrix_world.translation)
    widths = [crown_radius(obj) for obj in variants]
    spacing = args.get("spacing", 1.6 * float(numpy.mean(widths)))
    share, covered = forest_share(land, points, faces, args)
    placed = place_trees(ctx, args, camera, tree, faces, share, spacing, spheres, points)
    toward = switch_direction(placed, eye, tree, camera, args["near"])
    grove = forest_grove.Grove(ctx.scene, bake_collections, spheres, args["frames"], spacing, sun_direction(ctx.scene), args["seed"])
    calibration = grove.run(material, toward)
    forest_cards.set_gain(material, calibration["gain"])
    calibration["in_scene"] = calibrate_in_scene(ctx, args, camera, placed, spheres, trees_collection, material, calibration["gain"], len(variants))
    far = placed["far"]
    canopy_height = args.get("canopy_height", 0.85 * float(numpy.mean([height for _, _, height in spheres])))
    canopy = canopy_surface(land, points, eye, share, far, args["band"], canopy_height, atlases, final_gain(calibration), 2.0 * float(numpy.mean(widths)))
    group = bpy.data.objects.new(name, None)
    ctx.scene.collection.objects.link(group)
    near_count = int((placed["kind"] == 0).sum())
    near = near_trees(ctx, name, placed, spheres, trees_collection, group)
    cards, shadows = card_object(ctx, name, placed, spheres, args["frames"], len(variants), material, group, eye)
    ctx.scene.cycles.transparent_max_bounces = max(ctx.scene.cycles.transparent_max_bounces, TRANSPARENT_BOUNCES)
    group["blendworks_distant_forest"] = json.dumps({"land": land.name, "near": args["near"], "far": far, "band": args["band"]})
    ctx.view_layer.update()
    clipped = raise_all(ctx.scene, ctx.view_layer)
    return {
        "name": group.name,
        "near_trees": near.name if near is not None else None,
        "cards": cards.name if cards is not None else None,
        "shadow_cards": shadows.name if shadows is not None else None,
        "variants": [obj.name for obj in variants],
        "counts": {"near": near_count, "cards": int((placed["kind"] == 1).sum()), "canopy_candidates": int((placed["kind"] == 2).sum())},
        "cover": {"asked": args["cover"], "covered": rounded(covered, 4)},
        "spacing": rounded(spacing, 3),
        "switches": {"near": args["near"], "far": rounded(far, 3), "asked_far": args["far"], "band": args["band"]},
        "impostor": {"frames": args["frames"], "frame_pixels": args["frame_pixels"], "colour": colour_image.name,
                     "normal_depth": normal_image.name, "material": material.name},
        "calibration": calibration,
        "canopy": canopy,
        "cameras": clipped,
    }


def hidden_collection(ctx, name):
    if bpy.data.collections.get(name) is not None:
        raise bad_args(f"a collection named {name} already exists")
    collection = bpy.data.collections.new(name)
    ctx.scene.collection.children.link(collection)
    layer = ctx.view_layer.layer_collection.children[collection.name]
    layer.exclude = True
    return collection


def call(ctx, name, args):
    entry = COMMANDS[name]
    return entry.run(ctx, validate(entry.schema, args))


def grown_variants(ctx, args, collection):
    made = []
    points = max(LEAST_POINTS, int(GROWN_POINTS * args["tree_detail"]))
    for species in args["species"]:
        for variant in range(args["variants"]):
            index = len(made)
            skeleton = f"{args['name']}_grow_{index:02d}"
            seed = args["seed"] * 31 + index
            growth = {"name": skeleton, "preset": species, "seed": seed, "location": [0.0, 0.0, 0.0], "limit": 0}
            if TREE_PRESETS[species].get("method") == "colonization":
                growth["points"] = points
            call(ctx, "grow_tree", growth)
            bark = call(ctx, "tree_mesh", {"name": skeleton})["name"]
            leaves = call(ctx, "tree_leaves", {"name": bark, "leaves_name": f"{skeleton}_leaves", "seed": seed, "detail": "low"})["name"]
            call(ctx, "join", {"names": [bark, leaves], "target": bark})
            obj = bpy.data.objects[bark]
            call(ctx, "delete", {"names": [skeleton]})
            obj.name = f"{args['name']}_tree_{index:02d}"
            move_to(obj, collection)
            made.append(obj)
    return made


def copied_sources(args, collection):
    made = []
    for index, source in enumerate(args["sources"]):
        original = get_object(source)
        if original.type != "MESH":
            raise bad_args(f"{source} is not a mesh")
        obj = original.copy()
        obj.name = f"{args['name']}_tree_{index:02d}"
        obj.matrix_world = Matrix.Identity(4)
        obj.parent = None
        collection.objects.link(obj)
        made.append(obj)
    return made


def move_to(obj, collection):
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    obj.matrix_world = Matrix.Identity(4)


def crown_radius(obj):
    local = numpy.empty(len(obj.data.vertices) * 3, dtype=numpy.float32)
    obj.data.vertices.foreach_get("co", local)
    points = local.reshape(-1, 3)
    return float(numpy.hypot(points[:, 0], points[:, 1]).max())


SWITCH_SAMPLE = 64
PROBE_REACH = 2.0


def final_gain(calibration):
    in_scene = calibration.get("in_scene")
    return in_scene["gain"] if in_scene else calibration["gain"]


def calibrate_in_scene(ctx, args, camera, placed, spheres, collection, material, gain, variants):
    """The nearest cards, past the switch, drawn as trees and as cards in the scene itself to set the cards' gain."""
    eye = numpy.array(camera.matrix_world.translation)
    distance = numpy.linalg.norm(placed["base"] - eye, axis=1)
    cards = numpy.flatnonzero(placed["kind"] == 1)
    if len(cards) == 0:
        return None
    start = float(distance[cards].min())
    reach = (start, min(float(distance[cards].max()), PROBE_REACH * start))
    band = (placed["kind"] == 1) & (distance >= reach[0]) & (distance <= reach[1])
    context = (placed["kind"] < 2) & ~band

    def as_trees():
        return [near_trees(ctx, args["name"] + "_probe", dict(placed, kind=numpy.where(band | context, 0, 3)), spheres, collection, None)]

    def as_cards():
        trees = near_trees(ctx, args["name"] + "_probe", dict(placed, kind=numpy.where(context, 0, 3)), spheres, collection, None)
        return [trees] + list(card_object(ctx, args["name"] + "_probe", dict(placed, kind=numpy.where(band, 1, 3)), spheres, args["frames"], variants, material, None, eye))

    return forest_inplace.calibrate(ctx, camera, as_trees, as_cards, lambda value: forest_cards.set_gain(material, value), gain, reach)


def switch_direction(placed, eye, tree, camera, near):
    """Mean direction from the camera to the nearest cards, where trees turn into cards; straight ahead at the near
    distance when there are no cards."""
    cards = numpy.flatnonzero(placed["kind"] == 1)
    if len(cards) == 0:
        return calibration_direction(tree, camera, near)
    offsets = placed["base"][cards] - eye
    nearest = cards[numpy.argsort(numpy.linalg.norm(offsets, axis=1))[:SWITCH_SAMPLE]]
    directions = placed["base"][nearest] - eye
    mean = (directions / numpy.linalg.norm(directions, axis=1, keepdims=True)).mean(axis=0)
    return mean / numpy.linalg.norm(mean)


def calibration_direction(tree, camera, near):
    matrix = camera.matrix_world
    eye = numpy.array(matrix.translation)
    forward = -numpy.array(matrix.to_3x3().col[2])
    flat = numpy.array([forward[0], forward[1], 0.0])
    flat = flat / max(numpy.linalg.norm(flat), 1e-9) if numpy.linalg.norm(flat) > 1e-6 else numpy.array([0.0, 1.0, 0.0])
    target = eye + flat * near
    hit = tree.ray_cast(Vector((target[0], target[1], eye[2] + 1e5)), Vector((0.0, 0.0, -1.0)))
    ground = hit[0].z if hit[0] is not None else eye[2] - 2.0
    toward = numpy.array([target[0], target[1], ground]) - eye
    return toward / numpy.linalg.norm(toward)


def forest_share(land, points, faces, args):
    mesh = land.data
    normals = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
    mesh.vertex_normals.foreach_get("vector", normals)
    water = numpy.zeros(len(mesh.vertices), dtype=numpy.float32)
    if mesh.attributes.get(WATER_ATTRIBUTE) is not None:
        mesh.attributes[WATER_ATTRIBUTE].data.foreach_get("value", water)
    lift = numpy.zeros(len(mesh.vertices), dtype=numpy.float32)
    if mesh.attributes.get(LIFT_ATTRIBUTE) is not None:
        mesh.attributes[LIFT_ATTRIBUTE].data.foreach_get("value", lift)
    ground = points.copy()
    ground[:, 2] -= lift
    areas = forest_place.vertex_areas(points[:, :2], faces)
    return forest_place.forest_share(ground, normals.reshape(-1, 3).astype(numpy.float64), water.astype(numpy.float64), areas, args, args["patch_size"])


def place_trees(ctx, args, camera, tree, faces, share, spacing, spheres, points):
    eye = numpy.array(camera.matrix_world.translation)
    forward = -numpy.array(camera.matrix_world.to_3x3().col[2])[:2]
    forward = forward / numpy.linalg.norm(forward) if numpy.linalg.norm(forward) > 1e-6 else None
    data = camera.data
    half = math.atan(max(data.sensor_width, data.sensor_height) / (2.0 * data.lens)) if data.type == "PERSP" else math.pi
    reach = args["far"] * (1.0 + args["band"])
    xy, cells = forest_place.candidates(eye, forward, half, reach, spacing, args["seed"], args["view_only"])
    heights, forest = forest_place.ground_hits(tree, faces, share, xy, float(points[:, 2].max()) + 1000.0)
    chance = forest_place.cell_random(cells, args["seed"], 3)
    keep = ~numpy.isnan(heights) & (chance < forest)
    xy, cells, heights = xy[keep], cells[keep], heights[keep]
    base = numpy.column_stack([xy, heights - EMBED])
    distance = numpy.linalg.norm(base - eye, axis=1)
    keys = numpy.column_stack([forest_place.cell_random(cells, args["seed"], 4), forest_place.cell_random(cells, args["seed"], 5)])
    far = args["far"]
    order = numpy.sort(distance)
    if len(order) > args["budget"]:
        far = min(far, float(order[args["budget"] - 1]) / (1.0 + args["band"]))
    kind = forest_place.classes(distance, keys, args["near"], far, args["band"])
    if (kind < 2).sum() > args["budget"]:
        kind[numpy.argsort(distance)[args["budget"]:]] = 2
    count = len(spheres)
    variant = numpy.minimum((forest_place.cell_random(cells, args["seed"], 6) * count).astype(int), count - 1)
    scale = 0.8 + 0.4 * forest_place.cell_random(cells, args["seed"], 7)
    turn = 2.0 * math.pi * forest_place.cell_random(cells, args["seed"], 8)
    return {"base": base, "kind": kind, "variant": variant, "scale": scale, "turn": turn, "key": keys[:, 0], "far": far}


def near_trees(ctx, name, placed, spheres, collection, group):
    chosen = placed["kind"] == 0
    if not chosen.any():
        return None
    matrices = []
    for base, scale, turn in zip(placed["base"][chosen], placed["scale"][chosen], placed["turn"][chosen]):
        matrices.append(numpy.array(Matrix.Translation(Vector(base)) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Diagonal((scale, scale, scale, 1.0))))
    points = Placed(placed["base"][chosen], placed["variant"][chosen].astype(numpy.int32), placed["key"][chosen], numpy.array(matrices))
    return points_object(ctx, name + "_near", points, collection, group, False, False)


def card_object(ctx, name, placed, spheres, frames, variants, material, group, eye):
    """The cards facing the camera, hidden from shadow rays, and for a sun lamp a second set facing the sun that only
    casts shadows, so a card forest shades itself and the ground as the crowns would."""
    chosen = numpy.flatnonzero(placed["kind"] == 1)
    if len(chosen) == 0:
        return None, None
    cards = card_set(ctx, name + "_cards", placed, chosen, spheres, frames, variants, material, group, lambda pivot: eye)
    cards.visible_shadow = True
    sun = sun_direction(ctx.scene)
    if sun is None:
        cards.visible_shadow = True
        return cards, None
    shadows = card_set(ctx, name + "_shadows", placed, chosen, spheres, frames, variants, material, group, lambda pivot: pivot + sun * 1e6)
    for flag in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(shadows, flag, False)
    return cards, shadows


def sun_direction(scene):
    suns = [obj for obj in scene.objects if obj.type == "LIGHT" and obj.data.type == "SUN" and not obj.hide_render and obj.data.energy > 0.0]
    if not suns:
        return None
    strongest = max(suns, key=lambda obj: obj.data.energy)
    return numpy.array(strongest.matrix_world.to_3x3().col[2]).astype(numpy.float64)


def card_set(ctx, name, placed, chosen, spheres, frames, variants, material, group, viewer):
    trees = {"pivot": [], "turn": [], "view": [], "half": [], "variant": []}
    for index in chosen.tolist():
        centre, radius, _ = spheres[placed["variant"][index]]
        scale, turn = placed["scale"][index], placed["turn"][index]
        cos, sin = math.cos(turn), math.sin(turn)
        offset = numpy.array([cos * centre[0] - sin * centre[1], sin * centre[0] + cos * centre[1], centre[2]]) * scale
        pivot = placed["base"][index] + offset
        trees["pivot"].append(pivot)
        trees["turn"].append(turn)
        trees["view"].append(impostors.local_view(pivot, turn, viewer(pivot)))
        trees["half"].append(radius * impostors.CELL_MARGIN * scale)
        trees["variant"].append(int(placed["variant"][index]))
    mesh = forest_cards.card_mesh(name, trees, frames, variants)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    ctx.scene.collection.objects.link(obj)
    obj.parent = group
    return obj
