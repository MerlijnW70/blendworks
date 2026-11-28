"""Image helpers: colour space keys, size checks, lookup and loading."""

import array
import os

import bpy

from .errors import bad_args, failed, not_found
from .image_header import image_dimensions
from .limits import MAX_IMAGE_FILE_BYTES, MAX_IMAGE_SIZE

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".exr", ".webp")
COLORSPACES = {"srgb": "sRGB", "non_color": "Non-Color", "linear": "Linear Rec.709"}
COLORSPACE_KEYS = {value: key for key, value in COLORSPACES.items()}
DATA_COLORSPACES = ("Non-Color",)
ALPHA_DEPTHS = (32, 64, 128)
NOT_IMAGES = ("RENDER_RESULT", "COMPOSITING")


def colorspace_key(image):
    name = image.colorspace_settings.name
    return COLORSPACE_KEYS.get(name, name)


def is_data(image):
    return image.colorspace_settings.name in DATA_COLORSPACES


def check_size(width, height, what):
    if width < 1 or height < 1:
        raise bad_args(f"{what} has no pixels")
    if width > MAX_IMAGE_SIZE or height > MAX_IMAGE_SIZE:
        raise bad_args(f"{what} is {width}x{height} px; the cap is {MAX_IMAGE_SIZE} px per side")


def get_image(name):
    image = bpy.data.images.get(name)
    if image is None:
        raise not_found(f"no image named {name}; load one with image_load or make one with image_new")
    return image


def require_free_image_name(name):
    if name in bpy.data.images:
        raise bad_args(f"an image named {name} already exists")


def loaded_from(resolved):
    for image in bpy.data.images:
        if image.source == "FILE" and image.filepath_raw:
            path = os.path.realpath(bpy.path.abspath(image.filepath_raw))
            if os.path.normcase(path) == os.path.normcase(resolved):
                return image
    return None


def load_image(workspace, path, name=None, colorspace=None):
    resolved = workspace.existing(path, IMAGE_EXTENSIONS)
    if os.path.getsize(resolved) > MAX_IMAGE_FILE_BYTES:
        raise bad_args(f"{path} is larger than {MAX_IMAGE_FILE_BYTES} bytes")
    width, height = image_dimensions(resolved)
    check_size(width, height, path)
    if name is not None:
        require_free_image_name(name)
    image = bpy.data.images.load(resolved, check_existing=False)
    if name is not None:
        image.name = name
    image.use_fake_user = True
    if colorspace is None:
        colorspace = "linear" if resolved.lower().endswith(".exr") else "srgb"
    image.colorspace_settings.name = COLORSPACES[colorspace]
    actual = tuple(image.size)
    if actual == (0, 0):
        raise failed(f"Blender could not read {path}")
    check_size(actual[0], actual[1], path)
    return image


def image_file(image, workspace):
    if image.source != "FILE" or not image.filepath_raw:
        return None
    path = os.path.realpath(bpy.path.abspath(image.filepath_raw))
    return workspace.relative(path) if workspace.contains(path) else path


def image_summary(image, workspace):
    width, height = image.size
    return {
        "name": image.name,
        "size": [width, height],
        "channels": image.channels,
        "colorspace": colorspace_key(image),
        "float": image.is_float,
        "alpha": image.alpha_mode != "NONE" and image.depth in ALPHA_DEPTHS,
        "source": image.source.lower(),
        "file": image_file(image, workspace),
        "packed": image.packed_file is not None,
        "dirty": image.is_dirty,
        "users": image.users - int(image.use_fake_user),
    }


def read_pixels(image):
    width, height = image.size
    buffer = array.array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(buffer)
    return buffer


def holds_unsaved_pixels(image):
    return image.source == "GENERATED" or image.is_dirty


def set_colorspace(txn, image, name):
    if image.colorspace_settings.name == name:
        return
    previous = image.colorspace_settings.name
    keep = holds_unsaved_pixels(image)
    pixels = read_pixels(image) if keep else None

    def apply(target_name):
        image.colorspace_settings.name = target_name
        if pixels is not None:
            image.pixels.foreach_set(pixels)
            image.update()

    txn.on_rollback(lambda: apply(previous))
    apply(name)


def flipped_green(image, name):
    width, height = image.size
    pixels = read_pixels(image)
    pixels[1::4] = array.array("f", (1.0 - value for value in pixels[1::4]))
    copy = bpy.data.images.new(name, width, height, alpha=image.channels == 4, float_buffer=image.is_float)
    copy.colorspace_settings.name = "Non-Color"
    copy.pixels.foreach_set(pixels)
    copy.update()
    copy.pack()
    return copy


def new_image(name, width, height, color, alpha, float_buffer, colorspace):
    check_size(width, height, f"image {name}")
    image = bpy.data.images.new(name, width, height, alpha=alpha, float_buffer=float_buffer)
    if image.name != name:
        bpy.data.images.remove(image)
        raise bad_args(f"an image named {name} already exists")
    image.colorspace_settings.name = COLORSPACES[colorspace]
    rgba = list(color) + [1.0] * (4 - len(color))
    image.generated_color = rgba
    image.use_fake_user = True
    return image
