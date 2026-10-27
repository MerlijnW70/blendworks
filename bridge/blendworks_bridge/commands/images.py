import os

import bpy

from ..errors import bad_args, failed
from ..image_header import image_dimensions
from ..images import ALPHA_DEPTHS, COLORSPACES, NOT_IMAGES, get_image, image_summary, is_data, load_image, new_image
from ..limits import MAX_IMAGE_SIZE
from ..registry import command
from ..schema import boolean, color, integer, names, string

SAVE_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
TEMPORARY_SCENE = "blendworks_image_save"


@command(
    "image_load",
    "Load a PNG, JPEG, OpenEXR or WebP image from the workspace as a named image.",
    {
        "path": string("Image file inside the workspace, relative to it (.png, .jpg, .jpeg, .exr, .webp).", max_length=1024),
        "name": string("Image name. Default: the file name."),
        "colorspace": string(
            "srgb for colour maps, non_color for data maps (roughness, normal, height), linear for HDR colour. "
            "Default: linear for .exr files, srgb for the others.",
            list(COLORSPACES),
        ),
    },
    ["path"],
)
def image_load(ctx, args):
    image = load_image(ctx.workspace, args["path"], args.get("name"), args.get("colorspace"))
    return image_summary(image, ctx.workspace)


@command(
    "image_new",
    "Create a blank image filled with one colour, for example as a bake target.",
    {
        "name": string("Image name; must be new."),
        "width": integer("Width in pixels.", 1, MAX_IMAGE_SIZE, 1024),
        "height": integer("Height in pixels.", 1, MAX_IMAGE_SIZE, 1024),
        "color": color("Fill colour, RGB or RGBA from 0 to 1 (default opaque black).", [0.0, 0.0, 0.0, 1.0]),
        "alpha": boolean("Give the image an alpha channel.", True),
        "float": boolean("Store 32-bit float pixels instead of 8-bit.", False),
        "colorspace": string("Colour space. Default: srgb for 8-bit, linear for float.", list(COLORSPACES)),
    },
    ["name"],
)
def image_new(ctx, args):
    colorspace = args.get("colorspace") or ("linear" if args["float"] else "srgb")
    image = new_image(args["name"], args["width"], args["height"], args["color"], args["alpha"], args["float"], colorspace)
    return image_summary(image, ctx.workspace)


@command(
    "image_save",
    "Write an image into the workspace as PNG or JPEG; colour maps are written sRGB-encoded, data maps raw.",
    {
        "name": string("Image to save."),
        "path": string("File path inside the workspace, relative to it (.png, .jpg or .jpeg).", max_length=1024),
        "quality": integer("JPEG quality, 1 to 100.", 1, 100, 90),
        "depth": integer("Bits per channel: 8, or 16 for PNG.", 8, 16, 8),
        "relink": boolean("Point the image at the saved file afterwards, so exports and .blend files use it.", True),
    },
    ["name", "path"],
    writes_files=True,
    destructive_when="the file already exists",
)
def image_save(ctx, args):
    image = get_image(args["name"])
    extension = os.path.splitext(args["path"])[1].lower()
    if extension not in SAVE_FORMATS:
        raise bad_args("image_save writes .png, .jpg or .jpeg files")
    file_format = SAVE_FORMATS[extension]
    if args["depth"] not in (8, 16):
        raise bad_args("depth must be 8 or 16")
    if args["depth"] == 16 and file_format != "PNG":
        raise bad_args("16-bit depth needs a .png path")
    width, height = image.size
    if width == 0 or height == 0:
        raise failed(f"{image.name} has no pixels to save")
    path = ctx.workspace.output(args["path"], tuple(SAVE_FORMATS))
    data = is_data(image)
    write_image(image, path, file_format, args["depth"], args["quality"], data)
    if not os.path.isfile(path) or tuple(image_dimensions(path)) != (width, height):
        raise failed(f"saving {image.name} wrote no readable {file_format} file")
    if args["relink"]:
        relink(ctx.txn, image, path, data)
    result = image_summary(image, ctx.workspace)
    result.update({"path": ctx.workspace.relative(path), "bytes": os.path.getsize(path), "format": file_format.lower(), "depth": args["depth"]})
    return result


def write_image(image, path, file_format, depth, quality, data):
    scene = bpy.data.scenes.new(TEMPORARY_SCENE)
    try:
        settings = scene.render.image_settings
        settings.file_format = file_format
        alpha = file_format == "PNG" and image.depth in ALPHA_DEPTHS and image.alpha_mode != "NONE"
        settings.color_mode = "RGBA" if alpha else "RGB"
        settings.color_depth = str(depth)
        settings.quality = quality
        settings.color_management = "OVERRIDE"
        settings.display_settings.display_device = "sRGB"
        view = settings.view_settings
        view.view_transform = "Raw" if data else "Standard"
        view.look = "None"
        view.exposure = 0.0
        view.gamma = 1.0
        view.use_curve_mapping = False
        image.save_render(path, scene=scene)
    finally:
        bpy.data.scenes.remove(scene)


def relink(txn, image, path, data):
    saved = (image.source, image.filepath_raw, image.colorspace_settings.name)

    def restore():
        image.source = saved[0]
        image.filepath_raw = saved[1]
        image.colorspace_settings.name = saved[2]

    txn.on_rollback(restore)
    if image.packed_file is not None:
        image.unpack(method="REMOVE")
    image.filepath_raw = path
    image.source = "FILE"
    image.colorspace_settings.name = "Non-Color" if data else "sRGB"
    image.reload()


@command(
    "image_info",
    "List images with their size, colour space, file or packed state and number of users.",
    {"names": names("Images to report. Default: every image.")},
    mutates=False,
)
def image_info(ctx, args):
    if "names" in args:
        images = [get_image(name) for name in args["names"]]
        if len({image.name for image in images}) != len(images):
            raise bad_args("each image may be listed once")
    else:
        images = sorted((image for image in bpy.data.images if image.type not in NOT_IMAGES), key=lambda image: image.name)
    return {"images": [image_summary(image, ctx.workspace) for image in images]}
