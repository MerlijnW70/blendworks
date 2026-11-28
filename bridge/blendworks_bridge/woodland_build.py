"""Grows plant variants and instances them.

Grows the woodland's plant variants and instances them at the planned places. Trees and shrubs are grown once per
species, age class and variant by grow_trees in parallel worker sessions; ferns and herbs are built in code. Each
variant is one mesh (bark, twigs and leaves joined) in a hidden collection, and every plant of a layer is a point of one
instancer object that picks its variant, as ground cover does, so a thousand trees cost a few unique meshes."""
import math

import bpy
import numpy
from mathutils import Matrix, Vector

from .cover_nodes import points_object
from .registry import COMMANDS
from .schema import validate
from .woodland_plants import build_plants
from .woodland_species import BUILT_SHARE, CLASSES, grown_settings

LAYER_NAMES = ("trees", "shrubs", "herbs", "ferns")
KLASS_NAMES = CLASSES + ("shrub", "herb", "fern")
EMBED = {"trees": 0.12, "shrubs": 0.06, "herbs": 0.02, "ferns": 0.02}
PLANT_SIZE = {"herbs": 1.0, "ferns": 0.8}
LOW_DETAIL_CLASSES = ("sapling",)
LOWERED_FIRST = ("young", "shrub", "mature")
FEWER_FIRST = ("sapling", "young", "shrub", "mature")
UNDERSTOREY_TRIANGLES = {"herbs": 400, "ferns": 900}
TRIANGLES = {
    "oak": {"mature": {"full": 1_125_474, "low": 481_452}, "young": {"full": 276_902, "low": 128_736}, "sapling": {"full": 20_546, "low": 20_546}},
    "birch": {"mature": {"full": 888_644, "low": 418_198}, "young": {"full": 247_660, "low": 127_798}, "sapling": {"full": 23_790, "low": 23_790}},
    "pine": {"mature": {"full": 698_188, "low": 541_204}, "young": {"full": 238_116, "low": 183_284}, "sapling": {"full": 39_356, "low": 39_356}},
    "willow": {"mature": {"full": 976_656, "low": 976_656}, "young": {"full": 244_264, "low": 244_264}, "sapling": {"full": 38_412, "low": 38_412}},
    "maple": {"mature": {"full": 357_292, "low": 241_244}, "young": {"full": 102_300, "low": 70_024}, "sapling": {"full": 10_172, "low": 10_172}},
    "olive": {"mature": {"full": 862_960, "low": 305_506}, "young": {"full": 249_560, "low": 90_036}, "sapling": {"full": 15_678, "low": 15_678}},
    "hazel": {"shrub": {"full": 125_500, "low": 68_690}},
    "hawthorn": {"shrub": {"full": 618_670, "low": 223_984}},
    "elder": {"shrub": {"full": 210_512, "low": 108_288}},
    "sallow": {"shrub": {"full": 285_154, "low": 134_314}},
}


def call(ctx, name, args):
    entry = COMMANDS[name]
    return entry.run(ctx, validate(entry.schema, args))


class Variants:
    """Variant keys (species, class) in build order, with the indices of their meshes in the layer's collection."""

    def __init__(self):
        self.keys = []
        self.slots = {}

    def add(self, key, count):
        self.slots[key] = list(range(len(self.keys), len(self.keys) + count))
        self.keys.extend([key] * count)


def woody_variants(plants, counts):
    """Variants per (species, class) key in build order; counts maps each class name to its number of variants."""
    trees, shrubs = Variants(), Variants()
    woody = plants["layer"] <= 1
    seen = sorted({(str(plants["species"][index]), int(plants["klass"][index])) for index in numpy.flatnonzero(woody).tolist()},
                  key=lambda key: (key[1], key[0]))
    for species, klass in seen:
        (shrubs if KLASS_NAMES[klass] == "shrub" else trees).add((species, klass), counts[KLASS_NAMES[klass]])
    return trees, shrubs


def tree_specs(name, layer, variants, settings, seed):
    specs = []
    for index, (species, klass) in enumerate(variants.keys):
        klass_name = KLASS_NAMES[klass]
        detail = settings["details"][klass_name]
        grow_name = f"{name}_{layer}_grow_{index:03d}"
        variant_seed = (seed * 7919 + index * 104729 + klass * 31) % 2_000_000_000
        grow = {"name": grow_name, "seed": variant_seed, "location": [0.0, 0.0, 0.0], "limit": 0,
                **grown_settings(species, BUILT_SHARE[klass_name], settings["points_share"])}
        specs.append({"grow": grow, "mesh": {}, "leaves": {"seed": variant_seed, **({"detail": "low"} if detail == "low" else {})}})
    return specs


def hidden_collection(ctx, name, parent=None):
    collection = bpy.data.collections.new(name)
    (parent or ctx.scene.collection).children.link(collection)
    if parent is None:
        ctx.view_layer.layer_collection.children[collection.name].exclude = True
    return collection


def gather_tree(ctx, grow_name, target_name, collection):
    """Join a grown tree's bark, twigs and leaves into one mesh named target_name in collection; drop its skeleton."""
    bark = bpy.data.objects[f"{grow_name}_bark"]
    parts = [obj.name for obj in bpy.data.objects if obj.name.startswith(f"{grow_name}_bark") and obj.type == "MESH" and obj is not bark]
    if parts:
        call(ctx, "join", {"names": [bark.name] + parts, "target": bark.name})
    skeleton = bpy.data.objects.get(grow_name)
    if skeleton is not None:
        call(ctx, "delete", {"names": [grow_name]})
    for owner in list(bark.users_collection):
        owner.objects.unlink(bark)
    collection.objects.link(bark)
    bark.name = target_name
    bark.data.name = target_name
    bark.matrix_world = Matrix.Identity(4)
    return bark


def grow_woody(ctx, name, variants, layer, settings, seed, collection):
    if not variants.keys:
        return [], None
    specs = tree_specs(name, layer, variants, settings, seed)
    batch = {"trees": specs, "parallel": settings["parallel"]}
    if "workers" in settings:
        batch["workers"] = settings["workers"]
    report = call(ctx, "grow_trees", batch)
    made = [gather_tree(ctx, spec["grow"]["name"], f"{name}_{layer}_{index:03d}", collection) for index, spec in enumerate(specs)]
    summary = {key: report[key] for key in ("workers", "seconds", "fallbacks", "worker_peak_memory")}
    return made, summary


def build_understorey(ctx, name, layer, count, seed, collection):
    made = []
    for index, mesh in enumerate(build_plants(ctx, name, layer[:-1], count, seed, PLANT_SIZE[layer])):
        obj = bpy.data.objects.new(f"{name}_{layer}_{index:03d}", mesh)
        collection.objects.link(obj)
        made.append(obj)
    return made


def triangles(objects):
    total = 0
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        total += len(mesh.loop_triangles)
    return total


class Placed:
    def __init__(self, positions, pick, key, matrices):
        self.positions, self.pick, self.key, self.matrices = positions, pick, key, matrices
        self.card = numpy.zeros(len(pick), dtype=numpy.int32)
        self.tint = numpy.zeros(len(pick))

    def __len__(self):
        return len(self.pick)


def instance_layer(ctx, name, layer, plants, chosen, picks, scales, heights, collection, group):
    if len(chosen) == 0:
        return None
    base = numpy.column_stack([plants["xy"][chosen], heights[chosen] - EMBED[layer]])
    matrices = []
    for position, turn, scale in zip(base.tolist(), plants["turn"][chosen].tolist(), scales.tolist()):
        matrices.append(numpy.array(Matrix.Translation(Vector(position)) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Diagonal((scale, scale, scale, 1.0))))
    placed = Placed(base, picks.astype(numpy.int32), plants["key"][chosen], numpy.array(matrices))
    return points_object(ctx, f"{name}_{layer}", placed, collection, group, False, False)


def variant_picks(plants, chosen, variants):
    picks = []
    for index in chosen.tolist():
        slots = variants.slots[(str(plants["species"][index]), int(plants["klass"][index]))]
        picks.append(slots[min(int(plants["key"][index] * len(slots)), len(slots) - 1)])
    return numpy.array(picks, dtype=numpy.int64)


def woody_scales(plants, chosen):
    return numpy.array([plants["share"][index] / BUILT_SHARE[KLASS_NAMES[int(plants["klass"][index])]] for index in chosen.tolist()])


def understorey_picks(plants, chosen, count):
    return numpy.minimum((plants["key"][chosen] * count).astype(numpy.int64), count - 1)



def estimated_triangles(trees, shrubs, understorey, details, points_share):
    """Triangles the variants will hold, from TRIANGLES measured per species, class and leaf detail."""
    total = 0.0
    for variants in (trees, shrubs):
        for species, klass in variants.keys:
            klass_name = KLASS_NAMES[klass]
            total += TRIANGLES[species][klass_name][details[klass_name]] * points_share
    total += understorey * (UNDERSTOREY_TRIANGLES["herbs"] + UNDERSTOREY_TRIANGLES["ferns"])
    return int(math.ceil(total))


def fitted_plan(plants, variants, understorey, budget, count, points_share, asked, memory_of):
    """Variants and leaf detail that fit the triangle and memory budgets: full detail where asked, then lowered class
    by class (young, shrubs, mature), then fewer variants (saplings, young, shrubs, mature) down to one each."""
    details = {name: ("low" if asked == "low" or name in LOW_DETAIL_CLASSES else "full") for name in ("mature", "young", "sapling", "shrub")}
    counts = {name: variants for name in details}
    steps = [None] + [("detail", name) for name in LOWERED_FIRST] + [("variants", name) for name in FEWER_FIRST]
    for step in steps:
        if step is not None and step[0] == "detail":
            details[step[1]] = "low"
        elif step is not None:
            counts[step[1]] = 1
        trees, shrubs = woody_variants(plants, counts)
        estimate = estimated_triangles(trees, shrubs, understorey, details, points_share)
        if estimate <= budget["triangles"] and memory_of(estimate, count) <= budget["memory"]:
            break
    return trees, shrubs, details, counts, estimate
