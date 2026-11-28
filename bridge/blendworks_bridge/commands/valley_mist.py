"""The valley_mist command: a mist layer that lies in valleys and over water."""

import json

import bpy
import numpy

from .. import valley_mist as mist
from ..atmosphere_haze import DOMAIN_FLAG, box_mesh, extinction
from ..camera_reach import raise_all
from ..errors import bad_args
from ..land_region import Surface
from ..limits import FRACTION, MAX_ANISOTROPY, MAX_RELIEF, MAX_SEED
from ..limits_land import LEAST_MIST_CELLS, MAX_MIST_CELLS
from ..registry import command
from ..schema import CREATES, boolean, color, integer, length, names, number, point2, ref, string
from ..util import get_object, link_object, require_free_name, rounded

DEFAULT_NAME = "ValleyMist"


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
        "thickness": length("Thickness of the mist over the low ground, in metres.", 20.0, MAX_RELIEF),
        "fade": length("Soft top: metres over which the mist thins out above its thickness.", 10.0, MAX_RELIEF),
        "visibility": length("Visibility inside the mist, in metres.", 250.0),
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
    top, lowest = mist.mist_top(ground, cell, args["valley_width"], args["thickness"])
    settings = {"low": [float(low[0]), float(low[1])], "size": [2.0 * radius, 2.0 * radius], "fade": args["fade"],
                "visibility": args["visibility"], "tint": list(args["tint"]), "anisotropy": args["anisotropy"],
                "breakup": args["breakup"], "seed": args["seed"], "thickness": args["thickness"]}
    image = mist.top_image(name + mist.TOP_IMAGE_SUFFIX, top.astype(numpy.float32))
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
        "extinction_per_metre": rounded(extinction(args["visibility"]), 9),
        "low_ground": {"min": rounded(float(lowest.min()), 3), "max": rounded(float(lowest.max()), 3)},
        "ground": {"min": rounded(float(ground.min()), 3), "max": rounded(float(ground.max()), 3)},
        "coverage": rounded(mist.coverage(ground, top), 4),
        "bounds": {"min": [rounded(low[0]), rounded(low[1]), rounded(floor)], "max": [rounded(low[0] + 2 * radius), rounded(low[1] + 2 * radius), rounded(ceiling)]},
        "cameras": clipped,
        "cost": "path-traced volume in render_final; previews show it too",
    }


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
