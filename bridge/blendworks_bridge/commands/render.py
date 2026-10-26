import base64
import os
import shutil
import struct
import tempfile

import bpy

from .. import limits
from ..errors import bad_args, failed
from ..registry import command
from ..rig import TEMPORARY_PREFIX, VIEW_DIRECTIONS, PreviewRig, RenderSettings, stamp_fields
from ..schema import array, integer, string
from ..util import GEOMETRY_TYPES, get_object, scene_bounds

SEED = 0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_CHUNKS = (b"tEXt", b"zTXt", b"iTXt")


@command(
    "render_preview",
    "Render PNG previews (base64) from the active camera, a named camera, or turntable views fitted to the scene.",
    {
        "camera": string("Camera object to render from."),
        "views": array(
            {"type": "string", "enum": list(VIEW_DIRECTIONS)},
            "Turntable views with a camera fitted to the scene's bounds. Default without camera: the active camera, "
            "or three-quarter when there is none.",
            1,
            len(VIEW_DIRECTIONS),
        ),
        "resolution": integer("Image width and height in pixels.", 64, limits.MAX_RENDER_RESOLUTION, limits.DEFAULT_RENDER_RESOLUTION),
        "samples": integer("Render samples.", 1, limits.MAX_PREVIEW_SAMPLES, limits.DEFAULT_PREVIEW_SAMPLES),
        "engine": string("auto: Cycles on the CPU headless, EEVEE in the desktop add-on.", ["auto", "cycles", "eevee"], "auto"),
    },
    mutates=False,
)
def render_preview(ctx, args):
    if "camera" in args and "views" in args:
        raise bad_args("give camera or views, not both")
    if "views" in args and len(set(args["views"])) != len(args["views"]):
        raise bad_args("each view may be given once")
    scene = ctx.scene
    camera = None
    if "camera" in args:
        camera = get_object(args["camera"])
        if camera.type != "CAMERA":
            raise bad_args(f"{camera.name} is not a camera")
    elif "views" not in args and scene.camera is not None:
        camera = scene.camera
    views = args.get("views", ["three-quarter"]) if camera is None else None
    engine = choose_engine(ctx, args["engine"])
    settings = RenderSettings(scene)
    folder = tempfile.mkdtemp(prefix="blendworks-render-")
    try:
        with PreviewRig(scene) as rig:
            if not any(obj.type == "LIGHT" and obj.visible_get(view_layer=ctx.view_layer) for obj in scene.objects):
                rig.add_studio_lights()
            if scene.world is None:
                rig.add_grey_world()
            configure(scene, engine, args["resolution"], args["samples"])
            if camera is not None:
                images = [render_view(scene, camera, camera.name, folder)]
            else:
                rig.fitted_camera(scene_bounds(ctx, [obj for obj in scene.objects if obj not in rig.objects]))
                images = [render_view(scene, rig.point_camera(view), view, folder) for view in views]
    finally:
        settings.restore()
        shutil.rmtree(folder, ignore_errors=True)
    return {
        "images": images,
        "engine": "cycles" if engine == "CYCLES" else "eevee",
        "samples": args["samples"],
        "seed": SEED,
        "geometry_objects": sum(1 for obj in scene.objects if obj.type in GEOMETRY_TYPES),
    }


def choose_engine(ctx, requested):
    if requested == "cycles" or (requested == "auto" and not ctx.desktop):
        return "CYCLES"
    if bpy.app.background:
        raise bad_args("eevee needs the desktop add-on; headless sessions render with cycles")
    return "BLENDER_EEVEE"


def configure(scene, engine, resolution, samples):
    render = scene.render
    render.engine = engine
    render.resolution_x = resolution
    render.resolution_y = resolution
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
    image.file_format = "PNG"
    image.color_mode = "RGB"
    image.color_depth = "8"
    if engine == "CYCLES":
        cycles = scene.cycles
        cycles.device = "CPU"
        cycles.samples = samples
        cycles.seed = SEED
        cycles.use_animated_seed = False
        cycles.use_adaptive_sampling = False
        cycles.use_denoising = True
    else:
        scene.eevee.taa_render_samples = samples


def render_view(scene, camera, label, folder):
    scene.camera = camera
    path = os.path.join(folder, f"{len(os.listdir(folder))}.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if not os.path.isfile(path):
        raise failed(f"rendering {label} produced no image")
    with open(path, "rb") as handle:
        data = without_text_chunks(handle.read())
    return {
        "view": label,
        "camera": None if camera.name.startswith(TEMPORARY_PREFIX) else camera.name,
        "width": scene.render.resolution_x,
        "height": scene.render.resolution_y,
        "mimeType": "image/png",
        "data": base64.b64encode(data).decode("ascii"),
    }


def without_text_chunks(data):
    if data[:8] != PNG_SIGNATURE:
        raise failed("the renderer did not write a PNG")
    kept = [data[:8]]
    position = 8
    while position + 12 <= len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        end = position + 12 + length
        if kind not in TEXT_CHUNKS:
            kept.append(data[position:end])
        position = end
    return b"".join(kept)
