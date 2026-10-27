import base64
import os
import shutil
import struct
import tempfile

import bpy
from mathutils import Vector

from .. import device, limits
from ..errors import bad_args, failed
from ..preview import DIRECTIONS, SHADINGS, Shading, aim, frame_width, pixel_size
from ..registry import command
from ..rig import TEMPORARY_PREFIX, PreviewRig, RenderSettings, sphere_of, stamp_fields
from ..schema import array, integer, length, obj, string, vector3
from ..util import GEOMETRY_TYPES, get_object, object_bounds, scene_bounds, vec

SEED = 0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
TEXT_CHUNKS = (b"tEXt", b"zTXt", b"iTXt")
FORMATS = {"png": ("PNG", "image/png", ".png"), "jpeg": ("JPEG", "image/jpeg", ".jpg")}
FOCUS = obj(
    {
        "object": string("Object to frame; its bounds centre is the focus."),
        "point": vector3("Point to frame, in metres."),
        "width": length("Visible width at the focus, in metres. Default: the object's size, or 1 m around a point."),
        "direction": vector3("Direction from the focus towards the camera. Default: the views, or three-quarter."),
    }
)
FOCUS["description"] = "Close-up: frame an object or a point at a chosen width instead of the whole scene."


@command(
    "render_preview",
    "Render previews (base64 PNG or JPEG) from a camera, turntable views or a close-up focus, in a chosen shading.",
    {
        "camera": string("Camera object to render from."),
        "views": array(
            {"type": "string", "enum": list(DIRECTIONS)},
            "Turntable views with a camera fitted to the scene, or around focus. Default without camera: the active "
            "camera, or three-quarter when there is none.",
            1,
            len(DIRECTIONS),
        ),
        "focus": FOCUS,
        "shading": string(
            "shaded: scene materials; clay: grey; wireframe: clay with mesh edges; normals: world normals as colours; "
            "uv_checker: a UV grid; material_id: a flat colour per material.",
            SHADINGS,
            "shaded",
        ),
        "resolution": integer("Image width and height in pixels.", 64, limits.MAX_RENDER_RESOLUTION, limits.DEFAULT_RENDER_RESOLUTION),
        "samples": integer("Render samples.", 1, limits.MAX_PREVIEW_SAMPLES, limits.DEFAULT_PREVIEW_SAMPLES),
        "engine": string("auto: Cycles headless, EEVEE in the desktop add-on.", ["auto", "cycles", "eevee"], "auto"),
        "device": string("Cycles device. auto: GPU when usable, else CPU; gpu: fail without one; cpu. Default: BLENDWORKS_DEVICE or auto.", list(device.MODES)),
        "format": string("png, or jpeg for smaller results.", list(FORMATS), "png"),
        "quality": integer(f"JPEG quality. Default: {limits.DEFAULT_JPEG_QUALITY}.", 1, limits.MAX_JPEG_QUALITY),
    },
    mutates=False,
    slow=True,
)
def render_preview(ctx, args):
    check_arguments(args)
    scene = ctx.scene
    camera = chosen_camera(ctx, args)
    engine = choose_engine(ctx, args["engine"])
    choice = device.choose_device(device.requested_mode(args.get("device"))) if engine == "CYCLES" else None
    settings = RenderSettings(scene)
    quality = scene.render.image_settings.quality
    folder = tempfile.mkdtemp(prefix="blendworks-render-")
    report = {}
    try:
        with PreviewRig(scene) as rig, Shading(scene, ctx.view_layer, args["shading"]) as shading:
            subjects = [obj for obj in scene.objects if not obj.name.startswith(TEMPORARY_PREFIX)]
            if not any(obj.type == "LIGHT" and obj.visible_get(view_layer=ctx.view_layer) for obj in subjects):
                rig.add_studio_lights()
            if scene.world is None:
                rig.add_grey_world()
            configure(scene, engine, args)
            shots, distance = plan_shots(ctx, rig, camera, args, subjects, report)
            shading.apply([obj for obj in subjects if obj.visible_get(view_layer=ctx.view_layer)], pixel_size(distance, args["resolution"]) * 0.8)
            images, choice = render_all(scene, shots, folder, args, choice, rig)
            report.update(shading.report)
    finally:
        settings.restore()
        scene.render.image_settings.quality = quality
        shutil.rmtree(folder, ignore_errors=True)
    result = {
        "images": images,
        "engine": "cycles" if engine == "CYCLES" else "eevee",
        "device": choice.report() if choice is not None else {"device": "display", "backend": "EEVEE"},
        "device_label": choice.label() if choice is not None else "eevee on the display GPU",
        "shading": args["shading"],
        "samples": args["samples"],
        "seed": SEED,
        "geometry_objects": sum(1 for obj in scene.objects if obj.type in GEOMETRY_TYPES),
    }
    result.update(report)
    return result


def check_arguments(args):
    if "camera" in args and ("views" in args or "focus" in args):
        raise bad_args("give camera, or views and focus, not both")
    if "views" in args and len(set(args["views"])) != len(args["views"]):
        raise bad_args("each view may be given once")
    if "quality" in args and args["format"] != "jpeg":
        raise bad_args("quality applies to jpeg only")
    focus = args.get("focus")
    if focus is None:
        return
    if ("object" in focus) == ("point" in focus):
        raise bad_args("focus needs exactly one of object or point")
    if "direction" in focus:
        if "views" in args:
            raise bad_args("give focus.direction or views, not both")
        if Vector(focus["direction"]).length < 1e-9:
            raise bad_args("focus.direction must not be zero")


def chosen_camera(ctx, args):
    if "camera" in args:
        camera = get_object(args["camera"])
        if camera.type != "CAMERA":
            raise bad_args(f"{camera.name} is not a camera")
        return camera
    if "views" not in args and "focus" not in args:
        return ctx.scene.camera
    return None


def plan_shots(ctx, rig, camera, args, subjects, report):
    scene_centre, scene_radius = sphere_of(scene_bounds(ctx, subjects))
    if camera is not None:
        return [(camera, camera.name, None)], max((camera.matrix_world.translation - scene_centre).length, 0.01)
    focus = args.get("focus")
    directions = [(view, DIRECTIONS[view]) for view in args.get("views", ["three-quarter"])]
    if focus is None:
        rig.fitted_camera(scene_bounds(ctx, subjects))
        centre, distance = rig.centre, rig.distance
    else:
        centre, width = focus_target(ctx, focus)
        half = Vector((width, width, width)) / 2.0
        rig.fitted_camera((centre - half, centre + half))
        distance = frame_width(rig.camera.data, width, scene_radius + (scene_centre - centre).length)
        if "direction" in focus:
            directions = [("focus", Vector(focus["direction"]))]
        report["focus"] = {"centre": vec(centre), "width": round(width, 6), "distance": round(distance, 6)}
    return [(rig.camera, label, (centre, direction, distance)) for label, direction in directions], distance


def focus_target(ctx, focus):
    if "point" in focus:
        return Vector(focus["point"]), focus.get("width", 1.0)
    target = get_object(focus["object"])
    bounds = object_bounds(target, ctx.depsgraph())
    if bounds is None:
        return target.matrix_world.translation.copy(), focus.get("width", 1.0)
    low, high = bounds
    return (low + high) / 2.0, focus.get("width", max((high - low).length * 1.1, 0.01))


def choose_engine(ctx, requested):
    if requested == "cycles" or (requested == "auto" and not ctx.desktop):
        return "CYCLES"
    if bpy.app.background:
        raise bad_args("eevee needs the desktop add-on; headless sessions render with cycles")
    return "BLENDER_EEVEE"


def configure(scene, engine, args):
    render = scene.render
    render.engine = engine
    render.resolution_x = args["resolution"]
    render.resolution_y = args["resolution"]
    render.resolution_percentage = 100
    render.pixel_aspect_x = 1.0
    render.pixel_aspect_y = 1.0
    render.film_transparent = False
    render.use_border = False
    render.use_compositing = False
    render.use_sequencer = False
    for name in stamp_fields(render):
        setattr(render, name, False)
    image = render.image_settings
    image.file_format = FORMATS[args["format"]][0]
    image.color_mode = "RGB"
    if args["format"] == "png":
        image.color_depth = "8"
    else:
        image.quality = args.get("quality", limits.DEFAULT_JPEG_QUALITY)
    if engine == "CYCLES":
        cycles = scene.cycles
        cycles.samples = args["samples"]
        cycles.seed = SEED
        cycles.use_animated_seed = False
        cycles.use_adaptive_sampling = False
        cycles.use_denoising = True
    else:
        scene.eevee.taa_render_samples = args["samples"]


def render_all(scene, shots, folder, args, choice, rig):
    if choice is None:
        return [render_view(scene, shot, folder, args, rig) for shot in shots], None
    try:
        with device.DeviceScope(scene, choice):
            return [render_view(scene, shot, folder, args, rig) for shot in shots], choice
    except RuntimeError as error:
        if choice.device != "gpu" or device.requested_mode(args.get("device")) != "auto":
            raise failed(f"rendering on {choice.label()} failed: {error}") from error
        fallback = device.Choice("cpu", fallback=f"{choice.backend} did not render: {error}")
        with device.DeviceScope(scene, fallback):
            return [render_view(scene, shot, folder, args, rig) for shot in shots], fallback


def render_view(scene, shot, folder, args, rig):
    camera, label, aim_at = shot
    if aim_at is not None:
        centre, direction, distance = aim_at
        aim(camera, centre, direction, distance)
    scene.camera = camera
    rig.light_from(camera.matrix_world.to_3x3().normalized())
    file_format, mime_type, extension = FORMATS[args["format"]]
    path = os.path.join(folder, f"{len(os.listdir(folder))}{extension}")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(path):
        raise failed(f"rendering {label} produced no image")
    with open(path, "rb") as handle:
        data = handle.read()
    data = without_text_chunks(data) if file_format == "PNG" else checked_jpeg(data)
    return {
        "view": label,
        "camera": None if camera.name.startswith(TEMPORARY_PREFIX) else camera.name,
        "width": scene.render.resolution_x,
        "height": scene.render.resolution_y,
        "mimeType": mime_type,
        "data": base64.b64encode(data).decode("ascii"),
    }


def checked_jpeg(data):
    if data[:3] != JPEG_SIGNATURE:
        raise failed("the renderer did not write a JPEG")
    return data


def without_text_chunks(data):
    if data[:8] != PNG_SIGNATURE:
        raise failed("the renderer did not write a PNG")
    kept = [data[:8]]
    position = 8
    while position + 12 <= len(data):
        size, kind = struct.unpack(">I4s", data[position : position + 8])
        end = position + 12 + size
        if kind not in TEXT_CHUNKS:
            kept.append(data[position:end])
        position = end
    return b"".join(kept)
