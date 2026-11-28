"""The liquid_body command: ocean, lake, river and beach water at world scale."""

import math

import bpy
import numpy

from .. import liquid_bodies, liquid_grid, liquid_mesh, liquid_ocean, liquid_presets, liquid_ripples, liquid_river, liquid_shader, liquid_spectrum, liquid_world
from ..errors import bad_args
from ..kit_limits import MAX_PATH_POINTS
from ..limits import (BASE_NAME_LENGTH, FRACTION, LEAST_MANNING_N, LEAST_WAVE_CELLS, MAX_COORDINATE, MAX_FETCH,
                      MAX_LENGTH, MAX_MANNING_N, MAX_RELIEF, MAX_SEED, MAX_WAVE_CELLS, MAX_WIND_SPEED, PAIR, TURN)
from ..registry import COMMANDS, command
from ..schema import CREATES, EXISTS, array, boolean, described, integer, length, names, number, obj, point3, ref, string, validate, vector3
from ..util import get_mesh_object, link_object, require_free_name, vec

RIVER_STRETCH = 0.35
KINDS = ("ocean", "lake", "pond", "river", "puddle")
DEFAULT_PRESET = {"ocean": "water_sea", "lake": "water_fresh", "pond": "water_fresh", "river": "water_fresh", "puddle": "water_fresh"}
SHORE_WIDTH = {"ocean": 3.0, "lake": 0.8, "pond": 0.5, "river": 0.5, "puddle": 0.03}
WIND = described(obj({
    "speed": number("Wind speed at 10 m in m/s.", 0.0, MAX_WIND_SPEED),
    "direction": number("Compass direction the wind blows towards, degrees clockwise from north (+Y).", 0.0, TURN),
}), "Wind at the water. Default: the weather's (the drift of its lowest clouds and a speed for its storm value), else 2 m/s towards the east.")


def plan_liquid_body(args, state):
    """Plan hook: the body and its material share the name (default the kind), the ripple image is name_ripples,
    and an ocean beach without ground is the object and material name_beach."""
    name = args.get("name", args["kind"].capitalize())
    state.add("object", name)
    state.add("material", name)
    state.add("image", f"{name}_ripples")
    if args["kind"] == "ocean" and args["beach"] and "ground" not in args:
        state.add("object", f"{name}_beach")
        state.add("material", f"{name}_beach")


@command(
    "liquid_body",
    "Open water at world scale: ocean with wind waves and foam, lakes and ponds, rivers along a path or a terrain's lowest line, puddles in hollows.",
    {
        "kind": string("ocean, lake, pond, river or puddle.", list(KINDS)),
        "name": ref(string("Object name; its material gets the same name.", max_length=BASE_NAME_LENGTH), "object", CREATES),
        "preset": string("material_liquid preset. Default: water_sea for the ocean, water_fresh otherwise.", list(liquid_presets.PRESETS)),
        "ground": ref(names("Terrain or surface objects the water rests on (needed for lakes, ponds, rivers and puddles)."), "object", EXISTS),
        "level": number("Water level, world z in metres.", -MAX_COORDINATE, MAX_COORDINATE),
        "depth": length("Lake, pond, puddle: depth above the lowest ground of the hollow; river: depth of the channel.", None, MAX_LENGTH),
        "point": point3("Lake, pond, puddle: a spot in the hollow to fill; river: the source when no path is given."),
        "radius": length("Puddle: half the side of the area searched for the puddle (default 2 m)."),
        "resolution": length("Grid cell in metres. Default: a 400-node grid over the ground, 1 cm for puddles."),
        "overlap": number("How far the surface reaches under the ground at the shore, in metres, so the shoreline has no gap.", 0.0, MAX_RELIEF),
        "wind": WIND,
        "fetch": length("Ocean: open water upwind in metres (default 100 km). Lakes use their own length along the wind.", None, MAX_FETCH),
        "size": length("Ocean: side of the wave mesh in metres (default 400); flat rings carry it to the horizon."),
        "centre": array({"type": "number"}, "Ocean: centre of the wave mesh [x, y] (default the active camera's position).", 2, 2),
        "cells": integer(f"Ocean: cells along a side of the wave mesh (at most {MAX_WAVE_CELLS}).", LEAST_WAVE_CELLS, MAX_WAVE_CELLS),
        "choppiness": number("Ocean: horizontal crest sharpening of the waves, 0 to 1.", 0.0, FRACTION, 0.8),
        "horizon": boolean("Ocean: extend the surface with flat rings to the horizon.", True),
        "beach": boolean("Ocean without ground: add a sandy beach sloping 1:33 out of the water downwind.", False),
        "path": array(vector3("A point."), "River: centreline waypoints; z is ignored.", PAIR, MAX_PATH_POINTS),
        "width": length("River: channel width in metres.", 4.0),
        "carve": boolean("River: lower the ground into a channel and banks under the river.", True),
        "roughness": number("River: Manning's roughness n of the bed (0.035 for a natural stream).", LEAST_MANNING_N, MAX_MANNING_N, liquid_river.MANNING_NATURAL),
        "wet_shore": boolean("Darken and gloss the ground and rocks at the water line with the weather's wet-ground shading.", True),
        "shore_width": length("Width of the wet band above the water line in metres. Default by kind."),
        "shore_objects": ref(names("Objects to wet at the shore. Default: every mesh near the water."), "object", EXISTS),
        "seed": integer("Seed of the waves and ripples.", 0, MAX_SEED, 0),
    },
    ["kind"],
    slow=True,
    plan=plan_liquid_body,
    family="liquids",
    intents=("an ocean with waves and a beach", "a lake or pond in a terrain hollow", "a river flowing down a valley into a lake", "puddles after rain"),
    nearest=(("liquid_fill", "for liquid in a glass, bottle or other container"), ("material_liquid", "for only the material")),
)
def liquid_body(ctx, args):
    kind = args["kind"]
    name = args.get("name", kind.capitalize())
    require_free_name(name)
    stale = bpy.data.materials.get(name)
    if stale is not None:
        if stale.users > 0 or stale.get("blendworks_liquid") is None:
            raise bad_args(f"a material named {name} already exists; give another name")
        bpy.data.materials.remove(stale)
    preset_name = args.get("preset", DEFAULT_PRESET[kind])
    entry = liquid_presets.preset(preset_name)
    entry["preset"] = preset_name
    wind = liquid_world.scene_wind(ctx.scene, args.get("wind"))
    depsgraph = ctx.depsgraph()
    ground_objects = [get_mesh_object(item) for item in args.get("ground", [])]
    ground = liquid_grid.Ground(ground_objects, depsgraph) if ground_objects else None
    if kind != "ocean" and ground is None:
        raise bad_args(f"a {kind} needs ground")
    if kind == "ocean":
        built = ocean(ctx, args, ground, wind, entry)
    elif kind == "river":
        built = river(ctx, args, ground, ground_objects, wind, entry)
    else:
        built = basin(args, ground, wind, kind, entry)
    points, triangles, uvs, scalars, vectors, state, cell, report = built
    bottom = report.pop("bottom")
    points, triangles, top = liquid_mesh.close_sheet(points, triangles, bottom)
    uvs = numpy.concatenate([uvs, uvs])
    scalars = {key: numpy.concatenate([values, values]) for key, values in scalars.items()}
    vectors = {key: numpy.concatenate([values, values]) for key, values in (vectors or {}).items()}
    coordinates = "uv" if kind == "river" else "world"
    ripple_state = state if kind != "river" else report.pop("ripple_state")
    uv_scale = (report.get("width", 1.0), RIVER_STRETCH) if kind == "river" else (1.0, 1.0)
    ripple, tile = liquid_ripples.ripples(f"{name}_ripples", ripple_state, 0.0 if kind == "river" else wind["direction"], cell, args["seed"], coordinates, uv_scale)
    foam = {"attribute": "lq_foam"} if "lq_foam" in scalars and float(numpy.max(scalars["lq_foam"])) > 0.0 else None
    material = liquid_shader.build(name, entry, ripple if entry["mode"] == "clear" else None, foam)
    mesh = liquid_mesh.build_mesh(name, points, triangles, uvs, top=top, scalars=scalars, vectors=vectors)
    mesh.materials.append(material)
    body = link_object(ctx, name, mesh)
    liquid_mesh.flag(body, kind, {"preset": preset_name, "wind": wind, "level": report.get("level")})
    shore = None
    if args["wet_shore"] and (kind != "ocean" or ground is not None or "beach" in report):
        ctx.view_layer.update()
        shore = liquid_world.wet_shores(ctx, args.get("shore_width", SHORE_WIDTH[kind]), args.get("shore_objects"), body.name)
    sea = {"hs": round(state["hs"], 6), "peak_wavelength": round(liquid_spectrum.peak_wavelength(state["omega"]), 6), "regime": state["regime"]}
    if tile is not None:
        upwind, crosswind = liquid_ripples.slope_statistics(tile, wind["direction"] if kind != "river" else 0.0)
        sea["ripple_slopes"] = {"along": round(upwind, 6), "across": round(crosswind, 6)}
    result = {
        "name": body.name,
        "kind": kind,
        "preset": preset_name,
        "material": material.name,
        "wind": wind,
        "waves": sea,
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.polygons),
        "shore": shore,
    }
    result.update(report)
    return result


def sample_depth(points, level, ground):
    depth = numpy.empty(len(points))
    for index, (x, y) in enumerate(points[:, :2].tolist()):
        height = ground.height_at(x, y)
        depth[index] = (level[index] if numpy.ndim(level) else level) - height if not math.isnan(height) else 0.0
    return depth


def basin(args, ground, wind, kind, entry):
    filled = liquid_bodies.fill_basin(ground, args, kind)
    points, triangles = filled.sheet()
    fetch = liquid_bodies.fetch_along(filled.wet, filled.grid, wind["direction"])
    state = liquid_spectrum.sea_state(wind["speed"], max(fetch, filled.grid.cell))
    depth = sample_depth(points, filled.level, ground)
    if kind != "puddle":
        tile = liquid_bodies.mesh_tile(state, wind["direction"], filled.grid.cell, args["seed"], 0.0, fetch)
        heights, _, _ = liquid_bodies.wave_displacement(points, tile, state, numpy.maximum(depth, 0.0), 0.0)
        points[:, 2] += heights
    uvs = points[:, :2] - points[:, :2].min(axis=0)
    report = {
        "level": round(filled.level, 6),
        "area": round(filled.area, 6),
        "volume": round(filled.volume, 6),
        "max_depth": round(filled.max_depth, 6),
        "fetch": round(fetch, 6),
        "cell": filled.grid.cell,
        "bottom": float(numpy.nanmin(numpy.where(filled.wet, filled.heights, numpy.inf))) - max(0.05 * filled.max_depth, 2.0 * filled.overlap, 1e-3),
    }
    return points, triangles, uvs, {"lq_depth": depth}, None, state, filled.grid.cell, report


def ocean(ctx, args, ground, wind, entry):
    camera = ctx.scene.camera
    settings = dict(args)
    if "centre" not in settings:
        settings["centre"] = list(camera.matrix_world.translation[:2]) if camera is not None else [0.0, 0.0]
    level = args.get("level", 0.0)
    settings["level"] = level
    state = liquid_spectrum.sea_state(wind["speed"], args.get("fetch", 100_000.0))
    beach_ground = None
    report = {}
    if ground is None and args["beach"]:
        beach_ground = add_beach(ctx, args, settings, wind, level)
        report["beach"] = beach_ground.name
        ground = liquid_grid.Ground([beach_ground], ctx.depsgraph())
    elif args["beach"]:
        raise bad_args("beach is for an ocean without ground; the ground already gives the shore")
    points, triangles, uvs, scalars, built = liquid_ocean.build(settings, ground, state, wind, args["seed"])
    report.update(built)
    floor = level - float(numpy.max(numpy.where(scalars["lq_depth"] < liquid_ocean.OPEN_DEPTH, scalars["lq_depth"], 0.0))) - 1.0
    report.update({"level": level, "fetch": args.get("fetch", 100_000.0), "bottom": min(floor, level - 50.0) if ground is None else floor})
    return points, triangles, uvs, scalars, None, state, built["cell"], report


def add_beach(ctx, args, settings, wind, level):
    name = f"{args.get('name', 'Ocean')}_beach"
    require_free_name(name)
    size = args.get("size", 400.0)
    shore = settings["centre"][0] * math.sin(math.radians(wind["direction"])) + settings["centre"][1] * math.cos(math.radians(wind["direction"])) + size * 0.25
    points, triangles = liquid_ocean.beach_mesh(settings["centre"], size, level, wind["direction"], shore)
    mesh = liquid_mesh.build_mesh(name, points, triangles, points[:, :2] / 10.0)
    mesh.attributes.remove(mesh.attributes[liquid_world.TOP_ATTRIBUTE])
    beach = link_object(ctx, name, mesh)
    entry = COMMANDS["material_procedural"]
    entry.run(ctx, validate(entry.schema, {"name": name, "sand": {}}))
    mesh.materials.append(bpy.data.materials[name])
    return beach


def river(ctx, args, ground, ground_objects, wind, entry):
    width = args["width"]
    depth = args.get("depth", max(0.15 * width, 0.3))
    cell = args.get("resolution", liquid_bodies.default_cell(ground.low, ground.high, liquid_river.RIVER_NODES))
    grid = liquid_grid.Grid.covering(ground.low[:2], ground.high[:2], cell)
    heights = grid.sample(ground)
    water = liquid_world.Water([item for item in liquid_world.liquid_objects(ctx.scene)])
    excluded, mouth_level = liquid_river.under_water(grid, water)
    reached = False
    if "path" in args:
        line = numpy.asarray(args["path"])[:, :2]
    elif "point" in args:
        line, reached = liquid_river.lowest_line(grid, heights, args["point"], excluded if excluded.any() else None)
    else:
        raise bad_args("a river needs path or point (its source)")
    path = liquid_river.Path(liquid_river.chaikin(line), cell)
    mouth = mouth_level if (reached or (excluded.any() and "path" in args)) else None
    if mouth is not None:
        mouth = liquid_river.mouth_level(grid, water, path.xy[-1], width, mouth)
    liquid_river.levels(path, ground, depth, mouth, min(20.0 * width, path.length / 3.0), args["carve"])
    carved = 0
    if args["carve"]:
        carved = liquid_river.carve(ground_objects, path, width, depth)
        ground = liquid_grid.Ground(ground_objects, ctx.depsgraph())
        heights = grid.sample(ground)
    level, region, wet = liquid_river.region(grid, heights, path, width, args.get("overlap", 0.25 * cell), excluded)
    if not wet.any():
        raise bad_args("the river holds no water: the ground along its path lies above its level")
    points, triangles = liquid_grid.level_sheet(grid, heights, level, region, args.get("overlap", 0.25 * cell))
    flow, speed, uvs, foam, slope = liquid_river.flow_fields(path, points, width, depth, args["roughness"])
    surface_index, _, _ = path.nearest(points)
    depth_here = sample_depth(points, path.level[surface_index], ground)
    mean_speed = float(numpy.mean(liquid_river.manning_speed(depth, width, numpy.maximum(-numpy.gradient(path.level, path.s), liquid_river.MIN_SLOPE), args["roughness"])))
    state = liquid_spectrum.sea_state(0.0, 1.0)
    ripple_state = liquid_spectrum.sea_state(max(3.0 * mean_speed, 1.0), max(30.0 * width, 10.0))
    step = max(len(path.s) // 64, 1)
    rows = sorted(set(range(0, len(path.s), step)) | {len(path.s) - 1})
    report = {
        "ripple_state": ripple_state,
        "length": round(path.length, 6),
        "width": width,
        "depth": depth,
        "carved_vertices": carved,
        "mean_speed": round(mean_speed, 6),
        "joins": "water" if mouth is not None else None,
        "profile": [[round(float(path.s[row]), 4), round(float(path.level[row]), 4)] for row in rows],
        "path": [vec(list(path.xy[row]) + [float(path.level[row])]) for row in rows],
        "cell": cell,
        "bottom": float(numpy.nanmin(numpy.where(wet, heights, numpy.inf))) - max(0.1 * depth, 0.05),
    }
    return points, triangles, uvs, {"lq_depth": depth_here, "lq_speed": speed, "lq_foam": foam}, {"lq_flow": flow}, state, cell, report
