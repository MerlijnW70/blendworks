"""The valley_mist command: a mist layer that lies in valleys and over water."""

import json

import bpy
import numpy

from .. import sky_world, weather_build
from .. import valley_mist as mist
from ..atmosphere_haze import DOMAIN_FLAG, box_mesh, extinction
from ..camera_reach import raise_all
from ..errors import bad_args
from ..land_region import Surface
from ..limits import FRACTION, MAX_ANISOTROPY, MAX_RELIEF, MAX_SEED, MAX_WIND_SPEED, QUARTER_TURN, TURN, TWILIGHT_DEPTH
from ..limits_land import LEAST_MIST_CELLS, MAX_MIST_CELLS
from ..registry import command
from ..schema import CREATES, boolean, color, integer, length, names, number, obj, point2, ref, string
from ..util import get_object, link_object, require_free_name, rounded

DEFAULT_NAME = "ValleyMist"
CONDITIONS = obj(
    {
        "sun_elevation": number("Sun height in degrees. Default: the weather's or the sky's sun, else sunrise.", -TWILIGHT_DEPTH, QUARTER_TURN),
        "sun_azimuth": number("Sun azimuth in degrees from north; east of the meridian (0-180) the sun is rising.", 0.0, TURN),
        "wind": number(f"Wind at 10 m in m/s; mist needs at most {mist.WIND_LIMIT:.1f}. Default: the weather's, else {mist.DAWN['wind']:g}.", 0.0, MAX_WIND_SPEED),
        "humidity": number(f"Relative humidity 0-1 near the ground; mist needs {mist.HUMIDITY_LIMIT:g}. Default {mist.DAWN['humidity']:g}, a clear calm dawn.", 0.0, FRACTION),
        "cover": number(f"Cloud cover 0-1 overnight; mist needs at most {mist.COVER_LIMIT:g}. Default: the weather's, else 0.", 0.0, FRACTION),
    }
)
CONDITIONS["description"] = ("When the mist forms: light wind, moist air, a clear sky, night or early morning. It thins and lifts as the "
                             f"sun rises and is gone at {mist.BURN_OFF_ELEVATION:.1f} degrees, about 3 hours after sunrise.")


def plan_mist(args, state):
    name = args["name"]
    state.remove("object", name)
    state.remove("material", name)
    if not args["remove"]:
        state.add("object", name)
        state.add("material", name)


@command(
    "valley_mist",
    "Mist lying in valleys and over water: a layer of stated thickness and visibility over the low ground, following it up and down the land.",
    {
        "name": ref(string("Mist object; one of the same name is replaced.", default=DEFAULT_NAME), "object", CREATES),
        "ground": ref(names("Objects whose surfaces are the ground: terrain, distant land, water."), "object"),
        "centre": point2("Centre [x, y] of the misty square in metres. Default: the active camera."),
        "radius": length("Half the side of the misty square, in metres.", 3000.0),
        "cells": integer("Cells across the low-ground map.", LEAST_MIST_CELLS, MAX_MIST_CELLS, 256),
        "valley_width": length("Width in metres over which the low ground is the lowest ground: about a valley floor's width.", 300.0),
        "thickness": length(f"Thickness of the mist over the low ground, in metres. Default {mist.DEFAULT_THICKNESS:g}: valley mist is "
                            f"{mist.THICKNESS_RANGE[0]:g} to {mist.THICKNESS_RANGE[1]:g} m deep.", None, MAX_RELIEF),
        "fade": length("Soft top: metres over which the mist thins out above its thickness.", 10.0, MAX_RELIEF),
        "visibility": length(f"Visibility inside the fully formed mist, in metres. Default {mist.DEFAULT_VISIBILITY:.0f}: mist is "
                             f"{mist.VISIBILITY_RANGE[0]:g} to {mist.VISIBILITY_RANGE[1]:g} m (WMO); below 1000 m it is fog."),
        "conditions": CONDITIONS,
        "breakup": number("How much a seeded noise thins the mist into patches: 0 even, 1 patches.", 0.0, FRACTION, 0.4),
        "tint": color("Scatter colour, linear RGB.", [1.0, 1.0, 1.0], allow_alpha=False),
        "anisotropy": number("Forward scattering towards the sun.", -MAX_ANISOTROPY, MAX_ANISOTROPY, 0.6),
        "seed": integer("Random seed of the breakup.", 0, MAX_SEED, 0),
        "remove": boolean("Remove the mist of this name instead.", False),
    },
    plan=plan_mist,
    slow=True,
    family="photography",
    intents=("mist in the valley", "morning mist over the lake", "fog lying in low ground"),
    nearest=(("atmosphere", "for haze over the whole scene and a flat ground fog"), ("distant_land", "for land to the horizon")),
)
def valley_mist(ctx, args):
    name = args["name"]
    removed = remove(name)
    if args["remove"]:
        if "ground" in args or "centre" in args:
            raise bad_args("remove takes only name")
        return {"removed": removed}
    if "ground" not in args:
        raise bad_args("ground is required: the objects the mist lies on")
    require_free_name(name)
    conditions, sources = mist_conditions(ctx.scene, args.get("conditions", {}))
    formed = mist.formation(conditions)
    formed["conditions"] = conditions
    formed["sources"] = sources
    if not formed["forms"]:
        return {"name": None, "formed": formed}
    thickness = args.get("thickness", mist.DEFAULT_THICKNESS)
    visibility = args.get("visibility", mist.DEFAULT_VISIBILITY)
    objects = [get_object(item) for item in args["ground"]]
    if any(item.type != "MESH" for item in objects):
        raise bad_args("ground objects must be meshes")
    centre = args.get("centre")
    if centre is None:
        if ctx.scene.camera is None:
            raise bad_args("give centre, or add a camera")
        centre = list(ctx.scene.camera.matrix_world.translation)[:2]
    radius, cells = args["radius"], args["cells"]
    cell = 2.0 * radius / cells
    low = numpy.array(centre, dtype=numpy.float64) - radius
    xs = low[0] + (numpy.arange(cells) + 0.5) * cell
    ys = low[1] + (numpy.arange(cells) + 0.5) * cell
    grid_x, grid_y = numpy.meshgrid(xs, ys)
    surface = Surface(objects, ctx.depsgraph())
    ground = surface.heights(numpy.column_stack([grid_x.ravel(), grid_y.ravel()])).reshape(cells, cells)
    if numpy.isnan(ground).all():
        raise bad_args("the ground has no surface under the misty square")
    ground = numpy.where(numpy.isnan(ground), numpy.nanmax(ground), ground)
    top, lowest = mist.mist_top(ground, cell, args["valley_width"], thickness)
    top, base = mist.lifted(top, lowest, ground, thickness, formed["burnt"])
    settings = {"low": [float(low[0]), float(low[1])], "size": [2.0 * radius, 2.0 * radius], "fade": args["fade"],
                "visibility": visibility, "tint": list(args["tint"]), "anisotropy": args["anisotropy"],
                "breakup": args["breakup"], "seed": args["seed"], "thickness": thickness, "density": formed["density"],
                "lift": round(formed["burnt"] * thickness, 6)}
    image = mist.top_image(name + mist.TOP_IMAGE_SUFFIX, top.astype(numpy.float32), base.astype(numpy.float32))
    material = mist.mist_material(name, image, settings)
    floor = float(ground.min()) - 1.0
    ceiling = float(top.max()) + args["fade"] + 1.0
    mesh = box_mesh(name, (low[0], low[1], floor), (low[0] + 2.0 * radius, low[1] + 2.0 * radius, ceiling))
    mesh.materials.append(material)
    obj = link_object(ctx, name, mesh)
    obj.display_type = "WIRE"
    obj.hide_select = True
    obj[DOMAIN_FLAG] = True
    obj[mist.FLAG] = True
    obj[mist.PROPERTY] = json.dumps(settings)
    clipped = raise_all(ctx.scene, ctx.view_layer)
    return {
        "name": obj.name,
        "material": material.name,
        "image": image.name,
        "centre": [rounded(value) for value in centre],
        "cell": rounded(cell, 4),
        "extinction_per_metre": rounded(extinction(visibility) * formed["density"], 9),
        "thickness": rounded(thickness, 4),
        "visibility": rounded(visibility, 3),
        "formed": formed,
        "low_ground": {"min": rounded(float(lowest.min()), 3), "max": rounded(float(lowest.max()), 3)},
        "ground": {"min": rounded(float(ground.min()), 3), "max": rounded(float(ground.max()), 3)},
        "coverage": rounded(mist.coverage(ground, top), 4) if formed["burnt"] < 1.0 else 0.0,
        "bounds": {"min": [rounded(low[0]), rounded(low[1]), rounded(floor)], "max": [rounded(low[0] + 2 * radius), rounded(low[1] + 2 * radius), rounded(ceiling)]},
        "cameras": clipped,
        "cost": "path-traced volume in render_final; previews show it too",
    }


def mist_conditions(scene, given):
    """The conditions given, else the sky's sun and the weather's wind and cover, else a clear calm dawn."""
    air = weather_build.stored_air(scene)
    sky = sky_world.stored(scene.world)
    found = {}
    sources = {}
    known = {}
    if sky is not None:
        known.update({"sun_elevation": (sky["elevation"], "sky"), "sun_azimuth": (sky["azimuth"], "sky")})
    if air is not None:
        known.update({"wind": (air["wind"], "weather"), "cover": (air["cover"], "weather")})
    for key, dawn in mist.DAWN.items():
        if key in given:
            found[key], sources[key] = given[key], "given"
        else:
            found[key], sources[key] = known.get(key, (dawn, "dawn"))
    return found, sources


def remove(name):
    obj = bpy.data.objects.get(name)
    if obj is None or not obj.get(mist.FLAG):
        if obj is not None:
            raise bad_args(f"{name} exists and is not a valley mist")
        return False
    mesh = obj.data
    materials = [material for material in mesh.materials if material is not None]
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    for material in materials:
        tree = material.node_tree
        images = [item.image for item in tree.nodes if item.type == "TEX_IMAGE" and item.image is not None] if tree else []
        if material.users == 0:
            bpy.data.materials.remove(material)
        for image in images:
            if image.users == 0:
                bpy.data.images.remove(image)
    return True
