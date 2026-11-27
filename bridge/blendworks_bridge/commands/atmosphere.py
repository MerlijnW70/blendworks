import bpy
from mathutils import Vector

from .. import atmosphere_haze as haze
from ..errors import bad_args
from ..limits import MAX_ANISOTROPY, MAX_RELIEF
from ..registry import command
from ..schema import boolean, color, length, number, obj, string, vector3
from ..util import GEOMETRY_TYPES, object_bounds, rounded, vec

DOMAINS = ("box", "world")
METHODS = ("volume", "depth")
PREVIEWS = ("depth", "volume")
SAMPLE_DISTANCES = (10.0, 100.0, 1000.0)
FOG = obj(
    {
        "visibility": length("Visibility inside the fog at the base height, in metres."),
        "height": length("Height in metres over which the fog density falls to 1/e."),
    },
    ["visibility", "height"],
)
FOG["description"] = "Ground fog: a second, denser layer that hugs the ground."
BOUNDS = obj({"min": vector3("Lowest corner in metres."), "max": vector3("Highest corner in metres.")}, ["min", "max"])
BOUNDS["description"] = "Box domain corners. Default: the scene and its cameras, with a margin."


def plan_atmosphere(args, state):
    """Plan hook: the call removes the previous box domain and, for a box, makes the domain object and its material."""
    state.remove("object", haze.DOMAIN_NAME)
    state.remove("material", haze.MATERIAL_NAME)
    if not args["remove"] and args["domain"] == "box":
        state.add("object", haze.DOMAIN_NAME)
        state.add("material", haze.MATERIAL_NAME)


@command(
    "atmosphere",
    "Add aerial perspective and haze as a volume: visibility in metres, density falling with height, sun-scatter tint, ground fog.",
    {
        "visibility": length("Meteorological visibility at base_height in metres: where contrast falls to 2 %."),
        "height_falloff": length("Height in metres over which the density falls to 1/e. Default: uniform."),
        "base_height": number("Height in metres where the density equals the visibility.", -MAX_RELIEF, MAX_RELIEF, 0.0),
        "tint": color("Scatter colour: tints the sunlit haze; extinction per channel follows it.", [0.9, 0.95, 1.0], allow_alpha=False),
        "anisotropy": number("Forward scattering (0 even, 0.9 a tight glow around the sun).", -MAX_ANISOTROPY, MAX_ANISOTROPY, 0.5),
        "ground_fog": FOG,
        "domain": string("box: a bounded volume with height falloff; world: a uniform world volume.", DOMAINS, "box"),
        "bounds": BOUNDS,
        "method": string("volume: path-traced haze in render_final; depth: a cheap per-pixel haze from the depth pass.", METHODS, "volume"),
        "preview": string("How render_preview shows the haze: depth (fast) or volume.", PREVIEWS, "depth"),
        "airlight": color("Linear colour of the haze for the depth method. Default: the world's mean sky radiance.", allow_alpha=False),
        "remove": boolean("Remove the atmosphere instead.", False),
    },
    plan=plan_atmosphere,
    family="photography",
    intents=("light haze and aerial perspective", "fog in the valley", "distant hills fade into the sky", "volumetric mist"),
    nearest=(("set_world_hdri", "for the sky itself"), ("render_final", "to render the haze")),
)
def atmosphere(ctx, args):
    scene = ctx.scene
    if args["remove"]:
        if any(key in args for key in SETTINGS):
            raise bad_args("remove takes no other settings")
        return {"removed": remove(scene)}
    if "visibility" not in args:
        raise bad_args("visibility is required")
    check_arguments(args)
    remove(scene)
    settings = settings_from(ctx, args)
    if settings["domain"] == "box":
        material = haze.volume_material(settings)
        mesh = haze.box_mesh(haze.DOMAIN_NAME, *settings["bounds"])
        mesh.materials.append(material)
        domain = bpy.data.objects.new(haze.DOMAIN_NAME, mesh)
        scene.collection.objects.link(domain)
        domain.display_type = "WIRE"
        domain.hide_select = True
        domain[haze.DOMAIN_FLAG] = True
        settings["object"] = domain.name
    else:
        if scene.world is None or scene.world.node_tree is None:
            raise bad_args("the world volume needs a world with nodes; set one with set_world or set_world_hdri")
        haze.add_world_volume(scene.world, settings)
    haze.store(scene, settings)
    return report(settings)


SETTINGS = ("visibility", "height_falloff", "ground_fog", "bounds", "airlight")


def check_arguments(args):
    world = args["domain"] == "world"
    if world and ("height_falloff" in args or "ground_fog" in args or "bounds" in args):
        raise bad_args("a world volume is uniform: height_falloff, ground_fog and bounds need domain box")
    bounds = args.get("bounds")
    if bounds is not None and any(low >= high for low, high in zip(bounds["min"], bounds["max"])):
        raise bad_args("bounds.min must be below bounds.max on every axis")
    if "airlight" in args and args["method"] != "depth" and args["preview"] != "depth":
        raise bad_args("airlight only colours the depth method")


def remove(scene):
    settings = haze.stored(scene)
    removed = False
    if settings is not None:
        domain = haze.domain_object(settings)
        if domain is not None:
            mesh = domain.data
            materials = [material for material in mesh.materials if material is not None]
            bpy.data.objects.remove(domain, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            for material in materials:
                if material.users == 0:
                    bpy.data.materials.remove(material)
        haze.forget(scene)
        removed = True
    return haze.remove_world_volume(scene.world) or removed


def default_bounds(ctx):
    depsgraph = ctx.depsgraph()
    points = []
    for item in ctx.scene.objects:
        if item.type == "CAMERA":
            points.append(item.matrix_world.translation.copy())
        elif item.type in GEOMETRY_TYPES and item.visible_get(view_layer=ctx.view_layer):
            bounds = object_bounds(item, depsgraph)
            if bounds is not None:
                points.extend(bounds)
    if not points:
        raise bad_args("the scene is empty: give bounds for the atmosphere")
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    margin = max(max(high - low) * 0.1, 1.0)
    return [vec(low - Vector((margin, margin, margin))), vec(high + Vector((margin, margin, margin)))]


def settings_from(ctx, args):
    settings = {
        "visibility": args["visibility"],
        "height_falloff": args.get("height_falloff"),
        "base_height": args["base_height"],
        "tint": list(args["tint"]),
        "anisotropy": args["anisotropy"],
        "ground_fog": args.get("ground_fog"),
        "domain": args["domain"],
        "method": args["method"],
        "preview": args["preview"],
        "bounds": None,
    }
    if settings["domain"] == "box":
        bounds = args.get("bounds")
        settings["bounds"] = [list(bounds["min"]), list(bounds["max"])] if bounds is not None else default_bounds(ctx)
    settings["airlight"] = list(args["airlight"]) if "airlight" in args else haze.estimated_airlight(ctx.scene.world)
    return settings


def report(settings):
    base = settings["base_height"]
    sigma = haze.density_at(settings, base)
    result = {key: value for key, value in settings.items() if key != "object"}
    result["object"] = settings.get("object")
    result["extinction_per_metre"] = rounded(sigma, 9)
    result["transmittance"] = {
        f"{int(distance)} m": rounded(float(haze.transmittance(settings, base, base, distance).mean()))
        for distance in SAMPLE_DISTANCES
    }
    if settings["method"] == "volume":
        result["cost"] = "path-traced volume: slower renders, most with height falloff or ground fog; previews use " + settings["preview"]
    else:
        result["cost"] = "depth haze: almost free, no volume shadows or sun glow"
    return result
