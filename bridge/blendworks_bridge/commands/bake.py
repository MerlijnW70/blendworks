import time

import bpy

from .. import baking, device, limits
from ..errors import bad_args, failed
from ..images import require_free_image_name
from ..pbr import DEFAULT_OPTIONS, build_pbr
from ..registry import command
from ..schema import array, boolean, integer, names, number, obj, string
from ..util import get_mesh_object, get_objects, rounded

BAKING_SUFFIX = ".baking"
MAX_NAME_LENGTH = 63
PBR_KEYS = {"base_color": "base_color", "roughness": "roughness", "metallic": "metallic", "normal": "normal", "emission": "emission", "ao": "ao"}


def samples_schema():
    properties = {
        channel: integer(f"Samples for {channel} (default {count}).", 1, limits.MAX_BAKE_SAMPLES)
        for channel, count in baking.DEFAULT_SAMPLES.items()
    }
    schema = obj(properties)
    schema["description"] = "Samples per channel."
    return schema


@command(
    "bake",
    "Bake material channels of objects (or of high-poly sources onto one low-poly object) into images.",
    {
        "names": names("Objects to bake into the images; they share them, so their UVs must not overlap."),
        "channels": array(
            {"type": "string", "enum": list(baking.CHANNELS)},
            "Channels to bake: base_color, roughness, metallic and emission by emission; normal (tangent space) and ao.",
            1,
            len(baking.CHANNELS),
            ["base_color", "roughness", "metallic", "normal"],
        ),
        "size": integer("Image width and height in pixels.", 16, limits.MAX_BAKE_SIZE, limits.DEFAULT_BAKE_SIZE),
        "prefix": string("Image name prefix; images are named prefix_channel. Default: the first object's name."),
        "overwrite": boolean("Replace existing images of the same names after a successful bake.", False),
        "samples": samples_schema(),
        "margin": integer("Pixels to extend each island's border by.", 0, limits.MAX_BAKE_MARGIN, 16),
        "uv_map": string("UV map to bake into. Default: each mesh's active UV map."),
        "source": names("High-poly objects to bake from onto the single object in names (selected to active)."),
        "cage_extrusion": number("Selected to active: how far in metres rays start outside the low-poly surface.", 0.0, 10.0, 0.05),
        "max_ray_distance": number("Selected to active: longest ray in metres; 0 means no limit.", 0.0, 100.0, 0.0),
        "ao_distance": number("Reach in metres of the ao rays.", 0.001, 100.0, 1.0),
        "float_buffer": boolean("Bake data channels (roughness, metallic, normal, ao) into 32-bit float images.", False),
        "rewire": boolean("Give the objects one new material built from the baked images with material_pbr.", False),
        "material": string("Name of the rewired material. Default: prefix_baked."),
        "pack": boolean("Pack the baked images into the scene so .blend files keep them.", True),
        "device": string("auto: GPU when usable, else CPU; gpu: fail without a GPU; cpu. Default: BLENDWORKS_DEVICE or auto.", list(device.MODES)),
        "time_limit": number("Seconds; the bake fails and is undone once it runs longer.", 1.0, limits.MAX_BAKE_SECONDS, limits.DEFAULT_BAKE_SECONDS),
    },
    ["names"],
)
def bake(ctx, args):
    mode = device.requested_mode(args.get("device"))
    plan = make_plan(ctx, args)
    choice = device.choose_device(mode)
    started = time.monotonic()
    images = create_images(plan, args)
    settings = baking.SceneSettings(ctx.scene)
    swap = baking.EmissionSwap(plan["shading"])
    swap.check()
    targets = baking.TargetNodes(ctx, plan["targets"])
    report = []
    scope = device.DeviceScope(ctx.scene, choice)
    try:
        settings.prepare(args["ao_distance"] if "ao" in args["channels"] else None)
        targets.prepare()
        scope.__enter__()
        for channel in args["channels"]:
            check_time(started, args["time_limit"], channel)
            try:
                entry = bake_channel(ctx, channel, images[channel], plan, args, swap, targets)
            except RuntimeError as error:
                if choice.device != "gpu" or mode != "auto":
                    raise failed(f"baking {channel} failed: {error}") from error
                scope.__exit__(None, None, None)
                choice = device.Choice("cpu", fallback=f"{choice.backend} did not bake: {error}")
                scope = device.DeviceScope(ctx.scene, choice)
                scope.__enter__()
                entry = bake_channel(ctx, channel, images[channel], plan, args, swap, targets)
            report.append(entry)
            check_time(started, args["time_limit"], None)
    finally:
        swap.restore()
        targets.remove()
        scope.__exit__(None, None, None)
        settings.restore()
    final = finish_images(images, args)
    for entry in report:
        entry["image"] = final[entry["channel"]].name
    material = rewire(ctx, plan, final, args, swap.strength) if args["rewire"] else None
    return {
        "names": [obj.name for obj in plan["targets"]],
        "source": [obj.name for obj in plan["sources"]],
        "device": choice.report(),
        "device_label": choice.label(),
        "size": [args["size"], args["size"]],
        "channels": report,
        "images": [final[channel].name for channel in args["channels"]],
        "material": material,
        "seconds": rounded(time.monotonic() - started, 3),
    }


def make_plan(ctx, args):
    if len(set(args["channels"])) != len(args["channels"]):
        raise bad_args("each channel may be given once")
    targets = [get_mesh_object(name) for name in args["names"]]
    if len({obj.name for obj in targets}) != len(targets):
        raise bad_args("each object may be listed once")
    sources = get_objects(args["source"]) if "source" in args else []
    if sources:
        if len(targets) != 1:
            raise bad_args("a selected-to-active bake has exactly one object in names")
        if any(obj in targets for obj in sources):
            raise bad_args("an object cannot be both a source and the target")
        if any(obj.type != "MESH" for obj in sources):
            raise bad_args("bake sources must be meshes")
    elif args["cage_extrusion"] != 0.05 or args["max_ray_distance"] != 0.0:
        raise bad_args("cage_extrusion and max_ray_distance belong to a selected-to-active bake with source")
    for obj in targets:
        if len(obj.data.polygons) == 0:
            raise bad_args(f"{obj.name} has no faces to bake")
        layers = obj.data.uv_layers
        if "uv_map" in args and args["uv_map"] not in layers:
            raise bad_args(f"{obj.name} has no UV map named {args['uv_map']}")
        if len(layers) == 0:
            raise bad_args(f"{obj.name} has no UV map; unwrap it first")
    if "material" in args and not args["rewire"]:
        raise bad_args("material names the rewired material; set rewire to true")
    shading = sources or targets
    emission = [channel for channel in args["channels"] if channel in baking.EMISSION_SOURCES]
    materials = baking.shading_materials(shading, ", ".join(emission)) if emission else []
    if emission:
        baking.EmissionSwap(materials).check()
    for material in materials + [slot.material for obj in targets for slot in obj.material_slots if slot.material]:
        ctx.txn.touch_material_tree(material)
    for channel in args.get("samples", {}):
        if channel not in args["channels"]:
            raise bad_args(f"samples names {channel}, which is not baked")
    prefix = args.get("prefix", targets[0].name)
    return {"targets": targets, "sources": sources, "shading": materials, "prefix": prefix}


def create_images(plan, args):
    images = {}
    for channel in args["channels"]:
        name = f"{plan['prefix']}_{channel}"
        if len(name) + len(BAKING_SUFFIX) > MAX_NAME_LENGTH:
            raise bad_args(f"the image name {name} is too long; give a shorter prefix")
        if not args["overwrite"]:
            require_free_image_name(name)
        image = baking.bake_image(name + BAKING_SUFFIX, args["size"], args["size"], channel, args["float_buffer"])
        if image.name != name + BAKING_SUFFIX:
            raise bad_args(f"an image named {name + BAKING_SUFFIX} is in the way")
        images[channel] = image
    return images


def check_time(started, limit, channel):
    elapsed = time.monotonic() - started
    if elapsed > limit:
        where = f"before {channel}" if channel else "after a channel"
        raise failed(f"the bake ran {elapsed:.1f} s, over its time limit of {limit:.1f} s ({where}); nothing was kept")


def bake_channel(ctx, channel, image, plan, args, swap, targets):
    samples = args.get("samples", {}).get(channel, baking.DEFAULT_SAMPLES[channel])
    ctx.scene.cycles.samples = samples
    options = {
        "margin": args["margin"],
        "selected_to_active": bool(plan["sources"]),
        "cage_extrusion": args["cage_extrusion"],
        "max_ray_distance": args["max_ray_distance"],
        "uv_map": args.get("uv_map"),
    }
    active = plan["targets"][0]
    objects = plan["sources"] + plan["targets"]
    targets.point_at(image)
    if channel in baking.EMISSION_SOURCES:
        swap.apply(channel)
    started = time.monotonic()
    try:
        baking.run_bake_operator(ctx, channel, active, objects, options)
    finally:
        swap.restore()
        targets.clear()
    return {"channel": channel, "image": image.name, "samples": samples, "seconds": rounded(time.monotonic() - started, 3)}


def finish_images(images, args):
    final = {}
    for channel, image in images.items():
        name = image.name[: -len(BAKING_SUFFIX)]
        existing = bpy.data.images.get(name)
        if existing is not None:
            existing.user_remap(image)
            bpy.data.images.remove(existing)
        image.name = name
        if args["pack"]:
            image.pack()
        final[channel] = image
    return final


def rewire(ctx, plan, images, args, strength):
    name = args.get("material", f"{plan['prefix']}_baked")
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.use_fake_user = True
    else:
        ctx.txn.touch_material_tree(material)
    maps = {PBR_KEYS[channel]: image for channel, image in images.items()}
    options = dict(DEFAULT_OPTIONS)
    options["uv_map"] = args.get("uv_map")
    if "emission" in maps and strength is not None:
        options["emission_strength"] = strength
    build_pbr(material, maps, options)
    for obj in plan["targets"]:
        ctx.txn.touch_mesh(obj.data)
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.material_index = 0
    return material.name
