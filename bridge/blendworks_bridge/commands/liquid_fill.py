"""The liquid_fill command: fills a container with a liquid, with a meniscus and glass interface."""

import math

import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import liquid_cavity, liquid_container, liquid_extras, liquid_foam, liquid_grid, liquid_mesh, liquid_presets, liquid_shader
from ..errors import BridgeError, bad_args
from ..limits import (BASE_NAME_LENGTH, FRACTION, LEAST_CAVITY_VOXELS, LEAST_CONTACT_ANGLE, MAX_BUBBLES,
                      MAX_CAVITY_VOXELS, MAX_CONTACT_ANGLE, MAX_COORDINATE, MAX_DRIPS, MAX_LIQUID_TILT,
                      MAX_LIQUID_VOLUME, MAX_RELIEF, MAX_SEED, MAX_SPILL_AREA, MAX_WALL_GAP, TURN)
from ..registry import command
from ..schema import CREATES, EXISTS, boolean, described, integer, length, number, obj, point3, ref, string, vector3
from ..util import get_mesh_object, link_object, require_free_name, vec

LITRE = 0.001
GAP = 1e-4
DEPOSIT = "lq_deposit"
MAX_VOXELS = MAX_CAVITY_VOXELS
TILT = described(obj({
    "angle": number("Tilt of the liquid surface from level, in degrees, as in a sloshing or accelerating container.", 0.0, MAX_LIQUID_TILT),
    "direction": number("Compass direction the surface rises towards, in degrees.", 0.0, TURN, 0.0),
}), "Tilt the liquid's surface, as in a sloshing or accelerating container.")
SPILL = described(obj({
    "point": point3("Centre of the spill; it rests on the surface below."),
    "area": length("Area of the spill's footprint in square metres.", None, MAX_SPILL_AREA),
    "surface": ref(string("Object the spill lies on. Default: whatever is below the point."), "object", EXISTS),
    "contact_angle": number("Contact angle on the surface in degrees; with the capillary length it sets the thickness. Default: the preset's.", LEAST_CONTACT_ANGLE, MAX_CONTACT_ANGLE),
}, ["point", "area"]), "A spilled puddle of the liquid with a footprint of the given area, as thick as gravity and the contact angle make it.")
POUR = described(obj({
    "start": point3("Where the stream leaves the lip."),
    "velocity": vector3("Initial velocity of the liquid in m/s, at least 0.05 m/s (default 0.3 m/s straight down)."),
    "radius": length("Radius of the stream at the lip in metres.", 0.004),
}, ["start"]), "A free-falling stream from a lip down to the first surface it meets, narrowing as it speeds up.")
DRIPS = described(obj({
    "count": integer("Number of drips on the outside of the wall.", 1, MAX_DRIPS, 3),
    "band": length("Height below the rim where drips sit, in metres.", 0.04, MAX_RELIEF),
}, []), "Drops running down the outside of the container below its rim, longer for thicker liquids.")


def plan_liquid_fill(args, state):
    """Plan hook: the liquid's material (name, or name_preset when taken), its parts name_foam, name_bubbles,
    name_drips and name_pour with their materials, and the spill (name_spill beside a container, else name)."""
    name, preset = args["name"], args["preset"]
    if "container" in args:
        state.add("material", f"{name}_{preset}" if state.has("material", name) else name)
        entry = liquid_presets.preset(preset)
        if args.get("foam", (entry.get("foam") or {}).get("height", 0.0)) > 0.0:
            state.add("object", f"{name}_foam")
            state.add("material", f"{name}_foam")
        if args.get("bubbles", 120 if entry.get("bubbles") else 0) > 0:
            state.add("object", f"{name}_bubbles")
            state.add("material", f"{name}_bubble")
        for part in ("drips", "pour"):
            if part in args:
                state.add("object", f"{name}_{part}")
    if "spill" in args:
        spill = f"{name}_spill" if "container" in args else name
        film = f"{spill}_film" if "container" in args else spill
        state.add("object", spill)
        state.add("material", f"{film}_{preset}" if state.has("material", film) else film)


@command(
    "liquid_fill",
    "Fill a glass, bottle, cup, bowl, pan, bucket or tank with liquid to a level or volume in litres: meniscus, tilt, a thin gap to the wall, foam, drips, pour stream, spills.",
    {
        "container": ref(string("Container mesh, open or closed; its inner wall is found by voxels."), "object", EXISTS),
        "preset": string("material_liquid preset.", list(liquid_presets.PRESETS), "water_fresh"),
        "name": ref(string("Name of the liquid object; parts get suffixes (_foam, _drips, _pour, _spill, _bubbles).", default="Liquid", max_length=BASE_NAME_LENGTH), "object", CREATES),
        "level": number("Flat surface height (world z) away from the wall.", -MAX_COORDINATE, MAX_COORDINATE),
        "volume": length("Volume of liquid in litres.", None, MAX_LIQUID_VOLUME),
        "fill": number("Share of the container's capacity, 0 to 1.", 0.0, FRACTION),
        "tilt": TILT,
        "gap": number("Distance between the liquid and the inner wall in metres, so refraction renders through two separate surfaces.", 0.0, MAX_WALL_GAP, GAP),
        "meniscus": boolean("Raise the surface at the wall by the capillary rise of the preset (or depress it for a contact angle over 90 degrees).", True),
        "voxels": integer("Voxels across the container's largest side to find its cavity; doubled once by itself when the walls are too thin for it.", LEAST_CAVITY_VOXELS, MAX_VOXELS, 56),
        "glass": boolean("Give the container a glass material whose shadows let light through.", False),
        "foam": number("Foam head height in metres (beer has one by default; 0 for none).", 0.0, MAX_RELIEF),
        "bubbles": integer("Gas bubbles in the liquid (carbonated presets have 120 by default; 0 for none).", 0, MAX_BUBBLES),
        "drips": DRIPS,
        "pour": POUR,
        "spill": SPILL,
        "seed": integer("Seed of foam, bubbles, drips and spill outline.", 0, MAX_SEED, 0),
    },
    [],
    slow=True,
    plan=plan_liquid_fill,
    family="liquids",
    intents=("fill a glass with water or wine", "half a litre of milk in a jug", "beer with a foam head", "spilled coffee puddle on a table", "honey pouring from a spoon"),
    nearest=(("liquid_body", "for lakes, rivers, the ocean and puddles in terrain"), ("material_liquid", "for only the material")),
)
def liquid_fill(ctx, args):
    name = args["name"]
    entry = liquid_presets.preset(args["preset"])
    entry["preset"] = args["preset"]
    if "container" not in args and "spill" not in args:
        raise bad_args("give a container to fill, a spill, or both")
    capillary = liquid_presets.capillary_length(entry)
    result = {"name": None, "preset": args["preset"], "material": None, "capillary_length": round(capillary, 6)}
    if "container" in args:
        material = liquid_shader.build(free_material_name(name, args["preset"]), entry)
        result["material"] = material.name
        result.update(fill_container(ctx, args, entry, material, capillary))
    if "spill" in args:
        result["spill"] = add_spill(ctx, args, entry, capillary)
        result["name"] = result["name"] or result["spill"]["name"]
        result["material"] = result["material"] or result["spill"]["material"]
    return result


def free_material_name(name, preset):
    return name if bpy.data.materials.get(name) is None else f"{name}_{preset}"


def add_object(ctx, name, points, triangles, material, top=None, scalars=None):
    require_free_name(name)
    mesh = liquid_mesh.build_mesh(name, points, triangles, top=top, scalars=scalars)
    mesh.materials.append(material)
    created = link_object(ctx, name, mesh)
    return created


def fill_container(ctx, args, entry, material, capillary):
    container = get_mesh_object(args["container"])
    given = [key for key in ("level", "volume", "fill") if key in args]
    if len(given) != 1:
        raise bad_args("give exactly one of level, volume or fill")
    depsgraph = ctx.depsgraph()
    points, triangles, closed = liquid_cavity.container_arrays(container, depsgraph)
    angle = math.radians(entry["contact_angle"])
    rise = capillary * math.sqrt(2.0 * (1.0 - math.sin(angle))) if args["meniscus"] else 0.0
    meniscus = rise if entry["contact_angle"] <= 90.0 else -rise
    resolution = args["voxels"]
    try:
        voxels, rim, faces, pivot, walls, bottom, top, capacity = cavity(points, triangles, closed, resolution, args, meniscus, capillary)
    except BridgeError as first:
        resolution = min(2 * resolution, MAX_VOXELS)
        try:
            voxels, rim, faces, pivot, walls, bottom, top, capacity = cavity(points, triangles, closed, resolution, args, meniscus, capillary)
        except BridgeError:
            raise first from None
    if "level" in args:
        level = args["level"] - pivot[2]
        if not bottom < level < top:
            raise bad_args(f"level must lie between {round(bottom + pivot[2], 6)} and {round(top + pivot[2], 6)} (the bottom and the rim of the cavity)")
        built = liquid_container.build(walls, level, capillary, meniscus)
    else:
        target = args["volume"] * LITRE if "volume" in args else args["fill"] * capacity
        if target >= capacity:
            raise bad_args(f"{round(target / LITRE, 6)} l does not fit: the container holds {round(capacity / LITRE, 6)} l up to its rim")
        level, built = liquid_container.solve_level(walls, target, capillary, meniscus, bottom, top)
    local, faces_out, top_flags, volume = built
    world = walls.to_world(local)
    liquid = add_object(ctx, args["name"], world, faces_out, material, top_flags)
    if args["glass"]:
        report_glass = glass_interface(container)
    liquid_mesh.flag(liquid, "fill", {"preset": entry["preset"], "container": container.name})
    clearance = wall_clearance(world, voxels)
    report = {
        "name": liquid.name,
        "container": container.name,
        "volume_litres": round(volume / LITRE, 6),
        "capacity_litres": round(capacity / LITRE, 6),
        "level": round(level + pivot[2], 6),
        "meniscus": round(meniscus, 6),
        "gap": args["gap"],
        "clearance": round(clearance, 9),
        "inner_faces": int(len(faces)),
        "closed_container": closed,
        "voxel": round(voxels.size, 6),
        "voxels": resolution,
    }
    if args["glass"]:
        report["glass"] = report_glass
    extras(ctx, args, entry, material, world, faces_out, top_flags, voxels, points, triangles, rim, capillary, report)
    return report


def cavity(points, triangles, closed, resolution, args, meniscus, capillary):
    """The held space of the container on voxels of the given resolution, its inner wall offset by the gap, and its capacity."""
    voxels = liquid_cavity.Voxels(points, triangles, closed, resolution)
    rim = voxels.rim()
    faces = liquid_cavity.inner_faces(voxels, points, triangles)
    pivot = points[numpy.unique(faces)].mean(axis=0)
    walls = liquid_container.Walls(points, faces, args["gap"], liquid_container.tilt_matrix(args.get("tilt")), pivot)
    spill = rim - pivot[2] if not args.get("tilt", {}).get("angle") else math.inf
    top = min(walls.rim_low, spill) - (max(abs(meniscus), voxels.size) + voxels.size)
    bottom = walls.bottom + voxels.size * 0.25
    if top <= bottom:
        raise bad_args("the container is too shallow to hold liquid at this resolution; give more voxels")
    capacity = liquid_container.build(walls, top, capillary, 0.0)[3]
    return voxels, rim, faces, pivot, walls, bottom, top, capacity


def glass_interface(container):
    """Give the container glass whose shadows pass light, keeping its own smoothing but sharp edges past 30 degrees,
    so the shading normals of long wall faces do not bend refraction like a lens."""
    glass = liquid_shader.glass(f"{container.name}_glass")
    mesh = container.data
    mesh.materials.clear()
    mesh.materials.append(glass)
    mesh.set_sharp_from_angle(angle=math.radians(liquid_mesh.SMOOTH_ANGLE))
    mesh.update()
    return glass.name


def wall_clearance(world, voxels):
    best = math.inf
    for point in world.tolist():
        found = voxels.tree.find_nearest(Vector(point))
        if found[0] is not None:
            best = min(best, found[3])
    return best


def extras(ctx, args, entry, liquid_material, world, faces, top, voxels, points, triangles, rim, capillary, report):
    name = args["name"]
    foam_height = args.get("foam", (entry.get("foam") or {}).get("height", 0.0))
    if foam_height > 0.0:
        foam_points, foam_faces = liquid_foam.head(world, faces, top, foam_height, args["seed"])
        material = liquid_foam.foam_material(f"{name}_foam", entry)
        report["foam"] = add_object(ctx, f"{name}_foam", foam_points, foam_faces, material).name
    count = args.get("bubbles", 120 if entry.get("bubbles") else 0)
    if count > 0:
        tree = BVHTree.FromPolygons([Vector(point) for point in world], [tuple(face) for face in faces.tolist()])

        def contains(centre, size):
            hit = tree.find_nearest(Vector(centre))
            if hit[0] is None or hit[3] < size * 1.5:
                return False
            return (Vector(centre) - hit[0]).dot(hit[1]) < 0.0

        bubble_points, bubble_faces, placed = liquid_extras.bubbles(count, args["seed"], contains, world.min(axis=0), world.max(axis=0), 0.0006)
        if placed:
            material = liquid_foam.bubble_material(f"{name}_bubble", entry["ior"])
            report["bubbles"] = {"object": add_object(ctx, f"{name}_bubbles", bubble_points, bubble_faces, material).name, "count": placed}
    if "drips" in args:
        band = args["drips"].get("band", (rim - points[:, 2].min()) * 0.4)
        held = voxels.held()

        def outside(centre, normal):
            cell = voxels.index(centre + normal * voxels.size * 1.5)
            return cell is not None and not voxels.solid[cell] and not held[cell]

        outer = liquid_extras.outer_faces(points, triangles, rim, band, outside)
        drip_points, drip_faces, placed = liquid_extras.drips(outer, args["drips"]["count"], capillary, entry["viscosity"], args["seed"], rim)
        if placed:
            report["drips"] = {"object": add_object(ctx, f"{name}_drips", drip_points, drip_faces, liquid_material).name, "count": placed}
    if "pour" in args:
        report["pour"] = add_pour(ctx, args, liquid_material)


def scene_ray(ctx, exclude):
    depsgraph = ctx.depsgraph()

    def cast(a, b):
        direction = Vector(b) - Vector(a)
        distance = direction.length
        if distance <= 0.0:
            return None
        hit, location, _, _, hit_object, _ = ctx.scene.ray_cast(depsgraph, Vector(a), direction.normalized(), distance=distance)
        if hit and hit_object.name not in exclude:
            return location[:]
        return None

    return cast


def add_pour(ctx, args, material):
    pour = args["pour"]
    name = f"{args['name']}_pour"
    velocity = pour.get("velocity", [0.0, 0.0, -0.3])
    if math.sqrt(sum(value * value for value in velocity)) < 0.05:
        raise bad_args("a pour stream leaves the lip at 0.05 m/s or more; give a larger velocity")
    path, speeds, landed = liquid_extras.stream_path(pour["start"], velocity, scene_ray(ctx, {name}))
    if len(path) < 3:
        raise bad_args("the pour stream meets a surface at once; move start away from it")
    points, triangles, radii = liquid_extras.stream_mesh(path, speeds, pour.get("radius", 0.004))
    created = add_object(ctx, name, points, triangles, material)
    return {"object": created.name, "landed": landed, "end": vec(path[-1]), "radius_start": round(float(radii[0]), 6), "radius_end": round(float(radii[-1]), 6), "fall_speed": round(float(speeds[-1]), 6)}


def add_spill(ctx, args, entry, capillary):
    spill = args["spill"]
    name = f"{args['name']}_spill" if "container" in args else args["name"]
    require_free_name(name)
    depsgraph = ctx.depsgraph()
    if "surface" in spill:
        ground = liquid_grid.Ground([get_mesh_object(spill["surface"])], depsgraph)
    else:
        candidates = [item for item in ctx.scene.objects if item.type == "MESH" and item.get("blendworks_liquid") is None]
        if not candidates:
            raise bad_args("there is no surface for the spill to lie on")
        ground = liquid_grid.Ground(candidates, depsgraph)
    angle = spill.get("contact_angle", entry["contact_angle"])
    points, triangles, deposit, report = liquid_extras.spill(spill["point"], spill["area"], args["seed"], capillary, angle, ground.height_at, 1e-4)
    closed_points, closed_faces, top = liquid_mesh.close_sheet(points, triangles, float(points[:, 2].min()) - 1e-3)
    film = liquid_shader.build(free_material_name(name if "container" not in args else f"{name}_film", args["preset"]), entry, deposit={"attribute": DEPOSIT, "thickness": report["thickness"]})
    created = add_object(ctx, name, closed_points, closed_faces, film, top, {DEPOSIT: numpy.concatenate([deposit, numpy.zeros(len(deposit))])})
    liquid_mesh.flag(created, "spill", {"preset": entry["preset"]})
    return {"name": created.name, "material": film.name, "area": round(report["area"], 9), "thickness": round(report["thickness"], 6), "ring_width": round(report["ring_width"], 6), "contact_angle": angle}
