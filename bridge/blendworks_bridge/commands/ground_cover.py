"""The ground_element and ground_cover commands: layered grass, flowers and litter over a surface."""

import bpy
import numpy

from .. import liquid_masks
from ..cover_contact import contact_shading, write_contact
from ..cover_kinds import ELEMENT, FORMS, KINDS, MAX_ELEMENT_TRIANGLES, element_budget, element_params, make_element, material_names, require_free_materials
from ..cover_masks import camera_object
from ..cover_nodes import points_object, realized_vertices
from ..cover_plan import plan_cover
from ..cover_populations import KIND_POPULATION, MAX_POPULATIONS, POPULATION, kind_group, merged, resolved_populations
from ..cover_presets import PRESET_POPULATIONS
from ..cover_sampling import View, surface_tree
from ..cover_shading import CONTACT_DEFAULT
from ..errors import bad_args
from ..limits import (BASE_NAME_LENGTH, MAX_CONTACT_DARKENING, MAX_COVER_INSTANCES, MAX_DENSITY_SCALE, MAX_MESH_VERTICES,
                      MAX_SEED, MAX_VIEW_CAMERAS, MAX_VIEW_MARGIN)
from ..registry import command
from ..scatter_surface import read_surface
from ..schema import CREATES, EXISTS, array, boolean, described, integer, length, names, number, point3, ref, string
from ..util import get_mesh_object, link_object, require_free_name, vec

MAX_BUDGET = MAX_COVER_INSTANCES
CARD_BOUNCES = 512
FORM_LIST = {"geometry": ["geometry"], "cards": ["cards"], "auto": ["geometry", "cards"]}


BASE_SAMPLES = 8


def padded(points):
    return numpy.concatenate([points, numpy.repeat(points[:1], BASE_SAMPLES - len(points), axis=0)])


class ElementSet:
    def __init__(self, variants, has_both, objects, meshes):
        self.variants = variants
        self.has_both = has_both
        self.objects = objects
        self.base_radius = numpy.array([mesh.base_radius() for mesh in meshes])
        self.footprint = numpy.array([mesh.footprint() for mesh in meshes])
        self.triangles = numpy.array([mesh.triangles for mesh in meshes])
        self.vertices = numpy.array([len(mesh.points) for mesh in meshes])
        self.padded_bases = numpy.stack([padded(mesh.base_samples(BASE_SAMPLES)) for mesh in meshes])
        self.embedded = numpy.array([0.0 if mesh.flat() else 1.0 for mesh in meshes])


def plan_ground_element(args, state):
    """Plan hook: the element's materials are named after it."""
    for material in material_names(args["name"], args["kind"], args["form"]):
        state.add("material", material)


@command(
    "ground_element",
    "Build one ground-cover element for a meadow or forest floor in metres: a grass clump, tuft, sedge, wildflower, fallen leaf, twig or pebble, within a triangle budget.",
    {
        "kind": string("Element kind.", list(KINDS)),
        "form": string("geometry: real blades, petals and leaves; cards: alpha-mapped cards.", list(FORMS), "geometry"),
        "params": described(ELEMENT, "Element parameters in metres and degrees; each kind takes its own fields and has its own defaults."),
        "triangles": integer("Triangle budget; the generator fits its detail into it.", 1, MAX_ELEMENT_TRIANGLES),
        "seed": integer("Random seed; the same seed gives the same element.", 0, MAX_SEED, 0),
        "wind": boolean("Store the wind colours (see ground_cover) as the active colour attribute.", False),
        "name": ref(string("Name of the new object; its materials are named after it.", default="GroundElement"), "object", CREATES),
        "location": point3("Where the base of the element goes."),
    },
    ["kind"],
    slow=True,
    plan=plan_ground_element,
    family="ground_cover",
    intents=("one grass clump, tuft or sedge", "a single wildflower for a meadow", "a dry fallen leaf, twig or pebble for the forest floor"),
    nearest=(("ground_cover", "to cover a whole terrain with many elements"), ("tree_leaves", "for leaves on a tree")),
)
def ground_element(ctx, args):
    require_free_name(args["name"])
    require_free_materials(args["name"], args["kind"], args["form"])
    params = element_params(args["kind"], args.get("params", {}))
    budget = element_budget(args["kind"], args["form"], args.get("triangles"))
    data, mesh, report = make_element(args["name"], args["kind"], args["form"], params, args["seed"], budget, args["wind"], args["name"], {})
    obj = link_object(ctx, args["name"], data)
    if "location" in args:
        obj.location = args["location"]
    report.update({"name": obj.name, "kind": args["kind"], "form": args["form"], "materials": [material.name for material in data.materials], "wind": args["wind"]})
    return report


def build_elements(ctx, population, holder, prefix, seed, wind, cache):
    forms = FORM_LIST[population["form"]]
    collection = bpy.data.collections.new(f"{prefix}_elements")
    holder.children.link(collection)
    objects, meshes = [], []
    for form in forms:
        budget = element_budget(population["element"], form, population.get("triangles"))
        for variant in range(population["variants"]):
            index = len(objects)
            name = f"{prefix}_e{index:03d}"
            require_free_name(name)
            data, mesh, _ = make_element(name, population["element"], form, population["params"], seed * 7919 + variant, budget, wind, prefix, cache)
            obj = bpy.data.objects.new(name, data)
            collection.objects.link(obj)
            objects.append(obj)
            meshes.append(mesh)
    return collection, ElementSet(population["variants"], len(forms) == 2, objects, meshes)


def view_of(args):
    given = [key for key in ("camera", "cameras", "point") if key in args]
    if len(given) > 1:
        raise bad_args("give the falloff centre as one of camera, cameras or point")
    names_given = [args["camera"]] if "camera" in args else args.get("cameras", [])
    if args.get("view_only") and not names_given:
        raise bad_args("view_only needs a camera")
    if names_given:
        cameras = [camera_object(name) for name in names_given]
        return View([camera.matrix_world.translation[:] for camera in cameras], args["near"], args.get("far")), cameras
    if "point" in args:
        return View([args["point"]], args["near"], args.get("far")), []
    if "far" in args:
        raise bad_args("far needs a camera or point")
    return View(None, args["near"], None), []


def attributes_needed(target, depsgraph, populations):
    found = {}
    for population in populations:
        if "attribute" in population:
            name = population["attribute"]["name"]
            if name not in found:
                found[name] = read_surface(target, depsgraph, attribute=name).attribute
    return found


def element_holder(ctx, name):
    holder = bpy.data.collections.new(f"{name}_elements")
    ctx.scene.collection.children.link(holder)
    layer = ctx.view_layer.layer_collection.children.get(holder.name)
    if layer is not None:
        layer.exclude = True
    return holder


def plan_ground_cover(args, state):
    """Plan hook: the empty name, the hidden collection name_elements, and per population (preset and given) the
    object name_population, its collection, element objects name_population_e000 and on, and its materials."""
    name = args["name"]
    state.add("collection", f"{name}_elements")
    for entry in merged(args.get("preset"), args.get("populations", [])):
        if "element" not in entry:
            continue
        filled = dict(KIND_POPULATION[kind_group(entry["element"])], **entry)
        prefix = f"{name}_{entry['name']}"
        state.add("object", prefix)
        state.add("collection", f"{prefix}_elements")
        forms = FORM_LIST[filled["form"]]
        for index in range(len(forms) * filled["variants"]):
            state.add("object", f"{prefix}_e{index:03d}")
        for form in forms:
            for material in material_names(prefix, entry["element"], form):
                state.add("material", material)


@command(
    "ground_cover",
    "Cover a surface with layered ground cover (grass, tufts, sedges, flowers, leaves, twigs, pebbles) as instances: densities per m2, masks, clumps, a camera falloff and an instance budget.",
    {
        "target": ref(string("Mesh object to cover, in world space (modifiers included)."), "object", EXISTS),
        "name": ref(string("Name of the empty that holds the populations; each population is an object name_population.", default="GroundCover", max_length=BASE_NAME_LENGTH), "object", CREATES),
        "preset": string("Populations to start from: meadow, forest_floor, dry_steppe or lawn; populations of the same name change them.", list(PRESET_POPULATIONS)),
        "populations": array(POPULATION, "Layers of ground cover.", 1, MAX_POPULATIONS),
        "density_scale": number("Multiply every density, for a sparser or a test cover.", exclusive_minimum=0.0, maximum=MAX_DENSITY_SCALE, default=1.0),
        "obstacles": ref(names("Objects the cover keeps clear of where a population sets avoid: trunks, rocks."), "object", EXISTS),
        "trees": ref(names("Objects litter gathers under where a population sets under."), "object", EXISTS),
        "camera": ref(string("Camera whose position is the centre of the density falloff."), "object", EXISTS),
        "cameras": ref(names("Several cameras: the falloff counts from the nearest, and view_only keeps what any of them sees.", 1, MAX_VIEW_CAMERAS), "object", EXISTS),
        "point": point3("Centre of the density falloff instead of a camera."),
        "near": length("Full density up to this distance from the camera or point; beyond it the density falls as (near / distance)^2, so each screen area keeps about the same count.", 12.0),
        "far": length("No elements beyond this distance from the camera or point."),
        "view_only": boolean("Only place elements inside the camera's view.", False),
        "view_margin": number("view_only: margin around the frame, as a share of its size.", 0.0, MAX_VIEW_MARGIN, 0.1),
        "budget": integer("Most instances in all; when the populations would place more, the near distance shrinks (or, without a camera or point, every density) until they fit.", 1, MAX_BUDGET, 1_000_000),
        "seed": integer("Random seed; the same seed, surface and settings give the same cover.", 0, MAX_SEED, 0),
        "wind": boolean("Give every element the wind colours, an RGBA colour attribute named wind: R flutter, G phase, B main bend, A height share.", False),
        "contact_attribute": string("Point attribute written on the target: the share of ground the cover hides around each vertex, 0 to 1.", default="cover_density"),
        "darken": number("Darken the target's base colour by up to this share where the cover is full, through contact_attribute: the colour is multiplied by 1 - darken * cover, never below 0.64 (the darkest soil of the CC0 forest-ground photo against its median).", 0.0, MAX_CONTACT_DARKENING, CONTACT_DEFAULT),
        "realize": boolean("Realize the instances in the modifier instead of keeping them as instances.", False),
    },
    ["target"],
    slow=True,
    plan=plan_ground_cover,
    family="ground_cover",
    intents=("grass, wildflowers and leaf litter over terrain", "make a meadow, lawn, dry steppe or forest floor", "millions of grass blades with a camera falloff and an instance budget"),
    nearest=(("scatter", "for a few large objects such as rocks with Poisson spacing"), ("ground_element", "for one element")),
)
def ground_cover(ctx, args):
    target = get_mesh_object(args["target"])
    require_free_name(args["name"])
    populations, skipped = resolved_populations(args)
    for population in populations:
        require_free_name(f"{args['name']}_{population['name']}")
        for form in FORM_LIST[population["form"]]:
            require_free_materials(f"{args['name']}_{population['name']}", population["element"], form)
    view, cameras = view_of(args)
    depsgraph = ctx.depsgraph()
    surface = read_surface(target, depsgraph)
    if surface.area <= 0.0:
        raise bad_args("the target has no surface area to cover")
    liquid = liquid_masks.corner_depth(target, surface, depsgraph, max([population["shore"] for population in populations if population["liquid"] == "shore"], default=0.0))
    if liquid is None:
        skipped += [population["name"] for population in populations if population["liquid"] == "shore"]
        populations = [population for population in populations if population["liquid"] != "shore"]
        if not populations:
            raise bad_args("every population was skipped: shore populations need water from liquid_body or liquid_fill")
    context = {"liquid": liquid, "depsgraph": depsgraph, "obstacles": {}, "attributes": attributes_needed(target, depsgraph, populations), "cameras": cameras, "view_only": args["view_only"], "view_margin": args["view_margin"], "scene": ctx.scene}
    holder = element_holder(ctx, args["name"])
    cache, elements = {}, {}
    for population in populations:
        collection, element_set = build_elements(ctx, population, holder, f"{args['name']}_{population['name']}", args["seed"] + populations.index(population), args["wind"], cache)
        elements[population["name"]] = (collection, element_set)
    placed, reports, factor, start = plan_cover(surface, surface_tree(surface), populations, view, args["budget"], args["seed"], context, {name: entry[1] for name, entry in elements.items()})
    if args["realize"]:
        realized = sum(realized_vertices(elements[population["name"]][1].vertices, item.pick, item.key, 1.0) for population, item in zip(populations, placed))
        if realized > MAX_MESH_VERTICES:
            raise bad_args(f"realizing {sum(len(item) for item in placed)} instances would make {realized} vertices, more than the {MAX_MESH_VERTICES} allowed; keep the instances, or lower budget or density_scale")
    parent = link_object(ctx, args["name"], None)
    objects = []
    for population, item, report in zip(populations, placed, reports):
        collection, element_set = elements[population["name"]]
        report["elements"] = len(element_set.objects)
        report["triangles_per_element"] = [int(value) for value in element_set.triangles]
        report["triangles"] = int(element_set.triangles[item.pick].sum()) if len(item) else 0
        if len(item):
            objects.append(points_object(ctx, f"{args['name']}_{population['name']}", item, collection, parent, args["realize"], element_set.has_both or population["form"] == "cards").name)
    evaluated_count = len(target.evaluated_get(depsgraph).data.vertices)
    values = write_contact(target, surface, placed, args["contact_attribute"], evaluated_count)
    darkened, unchanged = contact_shading(target, args["contact_attribute"], args["darken"]) if values is not None and args["darken"] > 0.0 else ([], [])
    ctx.view_layer.update()
    if any(item.cards.any() for item in placed):
        ctx.scene.cycles.transparent_max_bounces = max(ctx.scene.cycles.transparent_max_bounces, CARD_BOUNCES)
    total = sum(len(item) for item in placed)
    result = {
        "name": parent.name,
        "count": total,
        "budget": args["budget"],
        "budget_factor": round(factor, 6),
        "populations": reports,
        "objects": objects,
        "elements_collection": holder.name,
        "triangles": sum(report["triangles"] for report in reports),
        "surface_area": round(surface.area, 6),
    }
    if view.origin is not None:
        result["falloff"] = {"centres": [vec(origin) for origin in view.origins], "near": round(factor * view.near, 6), "asked_near": view.near, "far": view.far}
    if skipped:
        result["skipped"] = skipped
    if values is None:
        result["contact"] = {"attribute": None, "note": "the target's modifiers change its vertex count, so no contact attribute was written"}
    else:
        result["contact"] = {"attribute": args["contact_attribute"], "mean": round(float(values.mean()), 6), "max": round(float(values.max()), 6), "darkened": darkened, "unchanged": unchanged}
    if total == 0:
        raise bad_args("no element fits: the masks removed every candidate")
    return result
