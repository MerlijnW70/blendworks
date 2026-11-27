import os
import shutil
import tempfile

import bpy

from .. import atmosphere_haze, camera_exposure, camera_reach, cloud_forms, device, exr_read, liquid_render, render_outputs, render_view, view_materials
from ..errors import bad_args
from ..limits import (FINAL_RESOLUTION, FINAL_SAMPLES, FRACTION, LEAST_BIT_DEPTH, MAX_BIT_DEPTH, MAX_FRAME, MAX_SEED,
                      PATH_LENGTH, RENDER_SECONDS, SHORTEST_RENDER_SECONDS, SHORTEST_SHUTTER_FRAMES, SHUTTER_FRAMES,
                      SMALLEST_RENDER_SIZE, THINNEST_WIRE, WIRE_WIDTH)
from ..registry import command
from ..rig import stamp_fields
from ..schema import array, boolean, integer, number, obj, ref, string
from ..util import get_object
from .camera_setup import camera_report

MAX_FINAL_RESOLUTION = FINAL_RESOLUTION
MAX_FINAL_SAMPLES = FINAL_SAMPLES
DEFAULT_FINAL_SAMPLES = 1024
CALL_TIMEOUT = 900
CALL_MAX_TIMEOUT = 1800
OVERHEAD_SECONDS = 300
MAX_FINAL_SECONDS = RENDER_SECONDS
DEFAULT_FINAL_SECONDS = 300.0
MIN_FINAL_SECONDS = SHORTEST_RENDER_SECONDS
OUTPUTS = {".png": "PNG", ".exr": "OPEN_EXR"}
MOTION_POSITIONS = {"start": "START", "center": "CENTER", "end": "END"}
MOTION = obj(
    {
        "shutter": number("Shutter in frames: how long the shutter is open (0.5 is a 180 degree shutter).", SHORTEST_SHUTTER_FRAMES, SHUTTER_FRAMES, 0.5),
        "position": string("Where the open shutter sits around the frame.", list(MOTION_POSITIONS), "center"),
    }
)
MOTION["description"] = "Motion blur for animated scenes: objects, cameras and deforming meshes smear over the shutter."


@command(
    "render_final",
    "Final-quality render from a camera into the workspace: up to 4096 px, adaptive sampling, denoising, time budget, passes.",
    {
        "path": string("Output file inside the workspace: .png (with exposure and look) or .exr (scene-linear).", max_length=PATH_LENGTH),
        "camera": ref(string("Camera object to render from. Default: the scene's active camera."), "object"),
        "width": integer("Image width in pixels.", SMALLEST_RENDER_SIZE, MAX_FINAL_RESOLUTION, 1920),
        "height": integer("Image height in pixels.", SMALLEST_RENDER_SIZE, MAX_FINAL_RESOLUTION, 1080),
        "samples": integer("Most samples per pixel.", 1, MAX_FINAL_SAMPLES, DEFAULT_FINAL_SAMPLES),
        "noise_threshold": number("Adaptive sampling stops a pixel below this noise; 0 turns adaptive sampling off.", 0.0, FRACTION, 0.01),
        "min_samples": integer("Samples before adaptive sampling may stop a pixel; 0 is automatic.", 0, MAX_FINAL_SAMPLES, 0),
        "denoise": boolean("Denoise with OpenImageDenoise, guided by albedo and normal passes.", True),
        "time_limit": number(
            f"Time budget in seconds for sampling; the render stops cleanly when it runs out. The call needs {OVERHEAD_SECONDS} s more "
            f"for scene sync, denoising, the extra pass render ({render_outputs.SURFACE_SECONDS:g} s at most) and writing, so its "
            f"timeout_seconds (default {CALL_TIMEOUT}, at most {CALL_MAX_TIMEOUT}) must stay at least time_limit + {OVERHEAD_SECONDS}.",
            MIN_FINAL_SECONDS,
            MAX_FINAL_SECONDS,
            DEFAULT_FINAL_SECONDS,
        ),
        "seed": integer("Noise seed; the same seed gives the same image on the same CPU.", 0, MAX_SEED, 0),
        "device": string("auto: GPU when usable, else CPU; gpu: fail without one; cpu. Default: BLENDWORKS_DEVICE or auto.", list(device.MODES)),
        "frame": integer("Frame to render. Default: the current frame.", -MAX_FRAME, MAX_FRAME),
        "motion_blur": MOTION,
        "passes": array(
            {"type": "string", "enum": list(render_outputs.PASS_NAMES)},
            "Extra passes: a multilayer <name>.passes.exr with every pass, plus a PNG view of each.",
            1,
            len(render_outputs.PASS_NAMES),
        ),
        "exr": boolean("Also write a scene-linear .exr next to a .png.", False),
        "depth": integer("Bits per channel of the .png: 8 or 16.", LEAST_BIT_DEPTH, MAX_BIT_DEPTH, 8),
        "transparent": boolean("Transparent background (alpha) instead of the world.", False),
        "preview": boolean("Return a small JPEG of the result to look at.", True),
        "shading": string(
            "shaded: the scene's materials; clay: one matte grey material on every surface, lit by the scene's own light and sky; "
            "wireframe: clay with the mesh's real edges drawn as lines of constant pixel width; normals: world-space normals as colours. "
            "Only surface materials change, keeping their transparency: the camera, lights, world, sky, clouds, haze, depth of field, "
            "motion blur, passes and outputs stay. Wireframe and normals are not denoised.",
            list(render_view.VIEWS),
            "shaded",
        ),
        "wire_width": number("shading wireframe: line width in pixels, the same at every distance.", THINNEST_WIRE, WIRE_WIDTH, view_materials.DEFAULT_WIRE_WIDTH),
        "wire_triangles": boolean("shading wireframe: also draw the diagonals the renderer cuts each quad and n-gon into.", False),
    },
    ["path"],
    mutates=False,
    renders=True,
    writes_files=True,
    destructive_when="an output file already exists",
    slow=True,
    timeout=CALL_TIMEOUT,
    max_timeout=CALL_MAX_TIMEOUT,
    family="photography",
    intents=(
        "final render at full resolution with denoising",
        "hero shot or beauty render into a file",
        "render depth, normal, albedo and object id passes",
        "render with motion blur",
        "clay render of a landscape or model without textures",
        "wireframe render, show the topology of a mesh of any size",
        "normals render, world-space normals as colours",
    ),
    nearest=(("render_preview", "for a quick look while working"), ("camera_setup", "for depth of field and exposure")),
)
def render_final(ctx, args):
    scene = ctx.scene
    camera = chosen_camera(scene, args)
    check_arguments(args)
    shading = args["shading"]
    if shading in render_view.UNDENOISED_VIEWS:
        args = dict(args, denoise=False)
    passes = list(dict.fromkeys(args.get("passes", [])))
    outputs = output_paths(ctx.workspace, args, passes)
    haze = atmosphere_haze.stored(scene)
    depth_haze = haze is not None and haze["method"] == "depth"
    surface_passes = haze is not None and not depth_haze and bool(passes)
    choice = device.choose_device(device.requested_mode(args.get("device")))
    scope = render_outputs.SettingsScope()
    folder = tempfile.mkdtemp(prefix="blendworks-final-")
    try:
        configure(scope, scene, ctx.view_layer, camera, args)
        liquids = liquid_render.configure(scope, scene)
        needed = [] if surface_passes else passes + (["depth"] if depth_haze and "depth" not in passes else [])
        taken = [name for name in outputs.values() if os.path.exists(name)]

        counter = render_outputs.SampleCounter()

        def work():
            with atmosphere_haze.VolumeHidden(scene, haze if depth_haze else None), counter:
                main = render_outputs.render_layers(scene, ctx.view_layer, folder, needed, counting=True)
            if not surface_passes:
                return main, main
            with atmosphere_haze.VolumeHidden(scene, haze), render_outputs.SurfacePasses(scene, args["samples"]):
                return main, render_outputs.render_layers(scene, ctx.view_layer, folder, passes, "surface.exr")

        with render_view.RenderView(scene, ctx.view_layer, shading, camera, args["wire_width"], args["wire_triangles"]) as view:
            with cloud_forms.FinalForm(scene) as cloud_form, camera_reach.ClipCovers(scene, ctx.view_layer, camera) as clip:
                (layers_path, passes_path), choice = render_outputs.on_device(scene, choice, args.get("device"), work)
            result = write_outputs(ctx, scene, camera, args, outputs, passes, haze, (layers_path, passes_path), folder, counter.most)
        result["shading"] = shading
        result.update(clip.report)
        result.update(view.report)
        result["overwritten"] = [ctx.workspace.relative(name) for name in taken]
        result["device"] = choice.report()
        result["device_label"] = choice.label()
    finally:
        frame = scene.frame_current
        scope.restore()
        if scene.frame_current != frame:
            scene.frame_set(scene.frame_current)
        shutil.rmtree(folder, ignore_errors=True)
    result["deterministic"], result["nondeterministic_because"] = determinism(choice, result["time_budget"])
    result["camera"] = camera_report(camera)
    result["view"] = camera_exposure.view_report(scene.view_settings)
    result["atmosphere"] = None if haze is None else {"method": haze["method"], "visibility": haze["visibility"]}
    result["clouds"] = cloud_forms.cloud_report(scene)
    result["liquids"] = liquids
    if result["clouds"] is not None and cloud_form.active:
        result["clouds"]["rendered_as"] = cloud_form.report()
    return result


def chosen_camera(scene, args):
    if "camera" in args:
        camera = get_object(args["camera"])
    else:
        camera = scene.camera
        if camera is None:
            raise bad_args("the scene has no active camera; give camera or add one with add_camera")
    if camera.type != "CAMERA":
        raise bad_args(f"{camera.name} is not a camera")
    return camera


def check_arguments(args):
    extension = os.path.splitext(args["path"])[1].lower()
    if extension not in OUTPUTS:
        raise bad_args("path must end in .png or .exr")
    if args["depth"] not in (8, 16):
        raise bad_args("depth must be 8 or 16")
    if extension == ".exr" and args["exr"]:
        raise bad_args("exr adds an .exr next to a .png; the path is already .exr")
    if args["min_samples"] > args["samples"]:
        raise bad_args("min_samples must not exceed samples")
    if "passes" in args and len(set(args["passes"])) != len(args["passes"]):
        raise bad_args("each pass may be given once")


def configure(scope, scene, view_layer, camera, args):
    render = scene.render
    cycles = scene.cycles
    scope.keep(scene, "camera", "frame_current")
    scope.keep(render, "engine", "resolution_x", "resolution_y", "resolution_percentage", "pixel_aspect_x", "pixel_aspect_y",
               "film_transparent", "use_border", "use_compositing", "use_sequencer", "use_motion_blur", "motion_blur_shutter",
               "motion_blur_position", *stamp_fields(render))
    scope.keep(cycles, "samples", "seed", "use_animated_seed", "use_denoising", "denoiser", "denoising_input_passes",
               "denoising_prefilter", "use_adaptive_sampling", "adaptive_threshold", "adaptive_min_samples", "time_limit")
    scope.keep(view_layer.cycles, "use_denoising")
    render.engine = "CYCLES"
    render.resolution_x = args["width"]
    render.resolution_y = args["height"]
    render.resolution_percentage = 100
    render.pixel_aspect_x = 1.0
    render.pixel_aspect_y = 1.0
    render.film_transparent = args["transparent"]
    render.use_border = False
    render.use_compositing = False
    render.use_sequencer = False
    for name in stamp_fields(render):
        setattr(render, name, False)
    cycles.samples = args["samples"]
    cycles.seed = args["seed"]
    cycles.use_animated_seed = False
    cycles.use_adaptive_sampling = args["noise_threshold"] > 0
    if args["noise_threshold"] > 0:
        cycles.adaptive_threshold = args["noise_threshold"]
        cycles.adaptive_min_samples = args["min_samples"]
    cycles.use_denoising = args["denoise"]
    view_layer.cycles.use_denoising = True
    if args["denoise"]:
        cycles.denoiser = "OPENIMAGEDENOISE"
        cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        cycles.denoising_prefilter = "ACCURATE"
    cycles.time_limit = args["time_limit"]
    motion = args.get("motion_blur")
    render.use_motion_blur = motion is not None
    if motion is not None:
        render.motion_blur_shutter = motion["shutter"]
        render.motion_blur_position = MOTION_POSITIONS[motion["position"]]
    scene.camera = camera
    if "frame" in args:
        scene.frame_set(args["frame"])


def output_paths(workspace, args, passes):
    """Every file the render may write, each resolved through the workspace check so no symlink leads out of it."""
    main = workspace.output(args["path"], tuple(OUTPUTS))
    stem = os.path.splitext(main)[0]
    outputs = {"main": main}

    def add(name, path, extensions):
        outputs[name] = workspace.output(path, extensions)

    if main.lower().endswith(".png") and args["exr"]:
        add("exr", stem + ".exr", (".exr",))
    if passes:
        add("passes", stem + ".passes.exr", (".exr",))
        for name in passes:
            add(name, f"{stem}.{render_outputs.PASS_FILES[name]}.png", (".png",))
    if len(set(os.path.normcase(path) for path in outputs.values())) != len(outputs):
        raise bad_args("two outputs would write the same file; choose another path")
    return outputs


def write_outputs(ctx, scene, camera, args, outputs, passes, haze, rendered_paths, folder, counted):
    layer = ctx.view_layer.name
    layers_path, passes_path = rendered_paths
    path = outputs["main"]
    metadata = exr_read.read_metadata(layers_path)
    depth_haze = haze is not None and haze["method"] == "depth"
    from_file = depth_haze or passes_path != layers_path
    sampled = exr_read.read_exr(layers_path, render_outputs.beauty_channels(layer, depth_haze))
    counts = render_outputs.sample_statistics(sampled, layer, args["samples"])
    if from_file:
        beauty = render_outputs.float_image("blendworks_final", render_outputs.beauty_pixels(scene, camera, sampled, layer, haze if depth_haze else None))
    else:
        beauty = bpy.data.images["Render Result"]
    del sampled
    files = {}
    try:
        alpha = args["transparent"]
        if path.lower().endswith(".png"):
            render_outputs.save_beauty(scene, beauty, path, "PNG", args["depth"], alpha)
            files["png"] = ctx.workspace.relative(path)
            preview_source = path
        else:
            preview_source = os.path.join(folder, "preview.png")
            render_outputs.save_beauty(scene, beauty, preview_source, "PNG", 8, alpha)
        if "exr" in outputs or path.lower().endswith(".exr"):
            exr_path = outputs.get("exr", path)
            render_outputs.save_beauty(scene, beauty, exr_path, "OPEN_EXR", 16, True)
            files["exr"] = ctx.workspace.relative(exr_path)
        preview = render_outputs.preview_image(preview_source, folder) if args["preview"] else None
    finally:
        if from_file:
            bpy.data.images.remove(beauty)
    written = {}
    if passes:
        surfaces = exr_read.read_exr(passes_path, render_outputs.pass_channels(layer, passes))
        written = render_outputs.write_passes(surfaces, layer, passes, outputs, ctx.workspace)
        del surfaces
        shutil.move(passes_path, outputs["passes"])
        files["passes"] = ctx.workspace.relative(outputs["passes"])
    rendered = render_outputs.rendered_samples(counted, metadata, layer)
    seconds = render_outputs.seconds_of(metadata.get(f"cycles.{layer}.render_time"))
    adaptive = args["noise_threshold"] > 0
    budget = render_outputs.budget_report(args["time_limit"], args["samples"], rendered, seconds, adaptive)
    result = {
        "files": files,
        "passes": written,
        "width": args["width"],
        "height": args["height"],
        "engine": "cycles",
        "samples": {"cap": args["samples"], "rendered": rendered, "per_pixel": counts, "adaptive": adaptive, "noise_threshold": args["noise_threshold"]},
        "denoise": {"denoiser": "openimagedenoise", "guides": ["albedo", "normal"]} if args["denoise"] else None,
        "time_budget": budget,
        "seed": args["seed"],
        "frame": scene.frame_current,
        "motion_blur": args.get("motion_blur"),
    }
    if preview is not None:
        result["preview"] = preview
    return result


def determinism(choice, budget):
    reasons = []
    if budget["stopped"]:
        reasons.append("the time budget stopped it: how many samples fit depends on the machine and its load")
    if choice.device == "gpu":
        reasons.append("the GPU: results may differ in the last bits between runs and drivers")
    return not reasons, reasons
