"""The tree_mesh command: one closed, UV-mapped bark mesh from a tree skeleton."""

import bpy

from ..errors import bad_args
from ..kit_limits import MAX_SEGMENTS
from ..limits import (ASPECT_RATIO, FEWEST_BRANCH_SIDES, FEWEST_RING_SEGMENTS_PER_METRE, LEAST_BARK_GRAIN, FEWEST_TRIANGLES, FRACTION, LINEAR_DENSITY, MAX_LENGTH,
                      MAX_RELIEF, RELIEF_SHARE, RINGS_BETWEEN_NODES, SWELLING, TRIANGLE_BUDGET)
from ..meshdata import MeshData
from ..noise_stack import STACK_FIELDS
from ..registry import command
from ..schema import CREATES, ENSURES, boolean, described, integer, length, number, obj, ref, string, validate, vector3
from ..topology import mesh_report
from ..tree_bark import build_bark, triangle_count
from ..tree_rings import BARK, ROOTS, WOOD
from ..tree_skeleton import FORMAT, PROPERTY, VERSION, from_property, plain
from ..tree_species import MESH as SPECIES_MESH, SPECIES_PROPERTY, species_material, species_of
from ..tree_surface import bark_noise, drop_helpers, face_materials, mark_sharp, self_overlaps, separate_touching, shell_count
from ..tree_twigs import twig_cards
from ..util import get_object, link_object, mesh_counts, require_free_name
from .procedural import ensure_material

MAX_BUDGET = TRIANGLE_BUDGET
DEFAULT_MIN_RADIUS = 0.004

RING_SEGMENTS = described(
    obj(
        {
            "min": integer("Fewest segments around a branch; thin twigs get this many.", FEWEST_BRANCH_SIDES, MAX_SEGMENTS, 6),
            "max": integer("Most segments around a branch; the trunk gets at most this many.", FEWEST_BRANCH_SIDES, MAX_SEGMENTS, 32),
            "per_metre": number("Segments per metre of circumference, so the count follows the radius between min and max.", FEWEST_RING_SEGMENTS_PER_METRE, LINEAR_DENSITY, 24.0),
        }
    ),
    "Segments around each branch by its radius, between a minimum and a maximum.",
)

FLARE = described(
    obj(
        {
            "amount": number("Extra radius at the trunk base as a share of the skeleton radius (Weber-Penn flare: 1 + amount (100^(1 - z / height) - 1) / 99).", 0.0, SWELLING, 0.5),
            "height": length("Height of the flare above the base in metres. Default 3 times the base radius.", maximum=MAX_RELIEF),
            "lobes": number("Share of the flare gathered towards the roots, so the base swells into buttresses.", 0.0, FRACTION, 0.6),
        }
    ),
    "Trunk-base flare.",
)

ROOT_FLARE = described(
    obj(
        {
            "amount": number("Extra radius of each root where it leaves the trunk, as a share of its skeleton radius, fading as (1 - s / length)^2.", 0.0, SWELLING, 1.5),
            "length": length("Distance along the root over which the swelling fades, in metres. Default 3 times the base radius."),
        }
    ),
    "Swelling of the roots where they join the trunk base.",
)

NOISE_FIELDS = {
    "amplitude": number("Largest bark displacement in metres; 0 turns it off.", 0.0, MAX_RELIEF, 0.05),
    "share": number("Bound on the displacement as a share of the local branch radius, so twigs are not torn.", 0.0, RELIEF_SHARE, 0.12),
    "grain": number("How much longer the bark features are along the branch than around it.", LEAST_BARK_GRAIN, ASPECT_RATIO, 3.0),
    **STACK_FIELDS,
    "scale": length("Wavelength of the first octave in metres.", 0.4),
    "hurst": number("Hurst exponent of the octaves.", 0.0, FRACTION, 0.55),
}

BARK_NOISE = described(obj(NOISE_FIELDS), "A noise_displace stack in metres along the vertex normals, faded to zero at the junctions.")

FIELDS = {
    "name": ref(string("Object that carries a tree skeleton: the grow_tree preview, or an object imported from a glb."), "object"),
    "mesh_name": ref(string("Name of the bark mesh. Default name_bark."), "object", CREATES),
    "junction": string("skin joins the generalised cylinders where they meet with an exact manifold union and keeps their rings and UVs; voxel rebuilds the union by a voxel remesh, smooths the junctions and maps the UVs back.", ["skin", "voxel"], "skin"),
    "voxel_size": length("voxel: cell size in metres. Default 0.3 times the thinnest kept radius."),
    "ring_segments": RING_SEGMENTS,
    "rings_per_segment": integer("Most rings between two skeleton nodes; rings sit about one edge apart along the branch.", 1, RINGS_BETWEEN_NODES, 3),
    "flare": FLARE,
    "root_flare": ROOT_FLARE,
    "collar": number("Branch collar: a branch swells by up to this share where it leaves a thicker parent, less the closer their radii.", 0.0, SWELLING, 0.5),
    "bark_noise": BARK_NOISE,
    "min_radius": number(f"Twigs thinner than this, in metres, are dropped (or made into cards); a branch cut short ends in fresh wood. Default {DEFAULT_MIN_RADIUS}, or the species' (birch, pine and willow keep their fine twigs).", 0.0, MAX_LENGTH),
    "twigs": string("drop leaves out the twigs under min_radius; cards adds them as crossed bark cards in a separate object name_twigs.", ["drop", "cards"], "drop"),
    "lod": integer("Target triangle budget; ring density (and if needed min_radius, or the voxel size) is chosen to meet it within 10 %.", FEWEST_TRIANGLES, MAX_BUDGET),
    "keep_skeleton": boolean("Keep the skeleton object (hidden) after building the mesh; false deletes it. The mesh carries the skeleton either way.", True),
    "view": vector3("Direction from the tree towards the viewer; UV seams go on the far side.", [0.0, -1.0, 0.0]),
    "bark_material": ref(string("Material for the bark; created when missing. Default bark, or species_bark (the species bark preset) for a tree grown from a species preset."), "material", ENSURES),
    "wood_material": ref(string("Material for cut ends; created when missing.", default="fresh_wood"), "material", ENSURES),
    "root_material": ref(string("Material for the roots; created when missing.", default="roots"), "material", ENSURES),
}

PLACEHOLDERS = {BARK: (0.12, 0.09, 0.07, 1.0), WOOD: (0.62, 0.48, 0.3, 1.0), ROOTS: (0.1, 0.075, 0.055, 1.0)}


def material_for(name, colour):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    material, _ = ensure_material(name)
    material.diffuse_color = colour
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = colour
        principled.inputs["Roughness"].default_value = 0.85
    return material


NESTED = ("ring_segments", "flare", "root_flare", "bark_noise")


def check_args(args, species=None):
    for key in NESTED:
        if key not in args:
            args[key] = validate(FIELDS[key], SPECIES_MESH.get(species, {}).get(key, {}))
    args.setdefault("min_radius", SPECIES_MESH.get(species, {}).get("min_radius", DEFAULT_MIN_RADIUS))
    if not any(args["view"]):
        raise bad_args("view must not be zero")
    rings = args["ring_segments"]
    if rings["min"] > rings["max"]:
        raise bad_args("ring_segments min must not exceed max")
    if args["junction"] != "voxel" and "voxel_size" in args:
        raise bad_args("voxel_size works only with junction voxel")


def twig_object(ctx, name, skeleton, twigs, material, matrix):
    cards = twig_cards(skeleton, twigs)
    if cards is None:
        return None
    points, corners, uvs = cards
    data = MeshData()
    for point in points.tolist():
        data.vertex(point)
    for face, face_uvs in zip(corners.tolist(), uvs.tolist()):
        data.face(face, face_uvs, smooth=True)
    mesh = bpy.data.meshes.new(name)
    data.to_mesh(mesh)
    mesh.materials.append(material)
    twigs_object = link_object(ctx, name, mesh)
    twigs_object.matrix_world = matrix
    return {"name": twigs_object.name, "cards": len(corners) // 2 if len(corners) else 0, "twigs": len(twigs)}


def finish_mesh(mesh, args):
    touching = separate_touching(mesh)
    noise = bark_noise(mesh, args["bark_noise"])
    used = sorted(set(face_materials_used(mesh)))
    mesh.materials.clear()
    face_materials(mesh, used)
    sharp = mark_sharp(mesh)
    pairs, _ = self_overlaps(mesh)
    drop_helpers(mesh)
    return used, {"touching": touching, "bark_noise": noise, "sharp_edges": sharp, "self_intersections": pairs}


def face_materials_used(mesh):
    values = [0] * len(mesh.polygons)
    mesh.attributes["tree_material"].data.foreach_get("value", values)
    return values


def plan_tree_mesh(args, state):
    """The bark object defaults to name_bark, with name_bark_twigs for twig cards; the default bark material follows
    the tree's species, which only the scene knows."""
    bark = args.get("mesh_name") or f"{args['name']}_bark"
    state.add("object", bark)
    if args["twigs"] == "cards":
        state.add("object", f"{bark}_twigs")
    if not args["keep_skeleton"]:
        state.remove("object", args["name"])
    if "bark_material" not in args:
        state.unknown(("material",))


@command(
    "tree_mesh",
    "Build one closed, UV-mapped bark mesh from a tree skeleton: generalised cylinders joined at smooth junctions, a flared base and roots, bark noise, lod budget.",
    FIELDS,
    ["name"],
    slow=True,
    family="natural",
    intents=(
        "turn a grown tree skeleton into a bark mesh",
        "watertight tree trunk and branches with smooth junctions",
        "flared trunk base with roots and bark UVs in metres",
        "game-ready tree mesh within a triangle budget",
    ),
    nearest=(("grow_tree", "to grow the skeleton first"), ("sweep", "for one tube along a path"), ("tree_leaves", "to add the foliage")),
    plan=plan_tree_mesh,
)
def tree_mesh(ctx, args):
    source = get_object(args["name"])
    species = species_of(source)
    check_args(args, species)
    if "bark_material" not in args:
        args["bark_material"] = f"{species}_bark" if species else "bark"
        if species:
            species_material(ctx, "bark", species, args["bark_material"])
    skeleton = from_property(source)
    name = args.get("mesh_name") or f"{source.name}_bark"
    require_free_name(name)
    if args["twigs"] == "cards":
        require_free_name(f"{name}_twigs")
    built = build_bark(ctx, skeleton, args, name)
    mesh = built.mesh
    used, finished = finish_mesh(mesh, args)
    names = {BARK: args["bark_material"], WOOD: args["wood_material"], ROOTS: args["root_material"]}
    for slot in used:
        mesh.materials.append(material_for(names[slot], PLACEHOLDERS[slot]))
    report = mesh_report(mesh)
    bark = link_object(ctx, name, mesh)
    bark.matrix_world = source.matrix_world.copy()
    bark[PROPERTY] = plain(source[PROPERTY])
    if species:
        bark[SPECIES_PROPERTY] = species
    twigs = None
    if args["twigs"] == "cards" and built.twigs:
        twigs = twig_object(ctx, f"{name}_twigs", skeleton, built.twigs, material_for(names[BARK], PLACEHOLDERS[BARK]), source.matrix_world.copy())
    if args["keep_skeleton"]:
        source.hide_set(True)
        source.hide_render = True
        kept = source.name
    else:
        kept = None
        bpy.data.objects.remove(source)
    ctx.view_layer.update()
    result = {
        "name": bark.name,
        "junction": args["junction"],
        "mesh": mesh_counts(mesh),
        "triangles": triangle_count(mesh),
        "manifold": report["manifold"],
        "volume": round(report["volume"], 9) if report["volume"] is not None else None,
        "shells": shell_count(mesh),
        "materials": [names[slot] for slot in used],
        "skeleton": {"property": PROPERTY, "format": FORMAT, "version": VERSION, "nodes": skeleton.count, "kept_on": kept},
        **built.summary(),
        **built.settings.resolved(),
        **finished,
    }
    if args.get("lod") is not None:
        result["lod"] = {"budget": args["lod"], "triangles": result["triangles"], "error": round(result["triangles"] / args["lod"] - 1.0, 6), "trials": result.pop("lod_trials")}
    if twigs is not None:
        result["twigs"] = twigs
    return result
