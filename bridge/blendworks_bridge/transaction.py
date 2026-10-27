import bpy
import numpy

from .errors import failed
from .limits import MAX_PIXEL_GUARD_BYTES
from .operators import window_context

MIN_UNDO_STEPS = 2
NOT_PIXELS = ("RENDER_RESULT", "COMPOSITING")


class NoSnapshot:
    snapshots = 0

    def touch_mesh(self, mesh):
        pass

    def touch_all_meshes(self):
        pass

    def touch_material(self, material, restore):
        pass

    def touch_material_tree(self, material):
        pass

    def on_rollback(self, restore):
        pass

    def guard_image_pixels(self):
        pass

    def begin(self):
        return self

    def commit(self):
        pass

    def rollback(self):
        pass


class Transaction(NoSnapshot):
    snapshots = 1

    def __init__(self, label, desktop):
        self.label = label
        self.desktop = desktop
        self.restores = []
        self.clean_images = set()
        self.pixel_copies = {}

    def on_rollback(self, restore):
        self.restores.append(restore)

    def begin(self):
        ensure_undo(self.desktop)
        undo_push(f"Blendworks: before {self.label}")
        self.clean_images = {image.name for image in bpy.data.images if not image.is_dirty}
        return self

    def guard_image_pixels(self):
        dirty = [image for image in bpy.data.images if image.type not in NOT_PIXELS and image.is_dirty and image.has_data]
        total = sum(image.size[0] * image.size[1] * image.channels * 4 for image in dirty)
        if total > MAX_PIXEL_GUARD_BYTES:
            raise failed(
                f"{len(dirty)} image(s) hold {total // (1024 * 1024)} MB of unsaved pixels, more than the "
                f"{MAX_PIXEL_GUARD_BYTES // (1024 * 1024)} MB a rollback can keep; save or pack them first"
            )
        for image in dirty:
            pixels = numpy.empty(len(image.pixels), dtype=numpy.float32)
            image.pixels.foreach_get(pixels)
            self.pixel_copies[image.name] = (tuple(image.size), pixels)

    def commit(self):
        if self.desktop:
            undo_push(f"Blendworks: {self.label}")
        self.restores = []
        self.pixel_copies = {}

    def rollback(self):
        for restore in reversed(self.restores):
            try:
                restore()
            except ReferenceError:
                pass
        self.restores = []
        undo_push(f"Blendworks: failed {self.label}")
        undo_back()
        self.restore_pixels()

    def restore_pixels(self):
        for image in bpy.data.images:
            if image.type in NOT_PIXELS:
                continue
            if image.name in self.pixel_copies:
                size, pixels = self.pixel_copies[image.name]
                if tuple(image.size) == size and len(image.pixels) == len(pixels):
                    image.pixels.foreach_set(pixels)
                    image.update()
            elif image.name in self.clean_images and image.is_dirty:
                image.reload()
        self.pixel_copies = {}


def ensure_undo(desktop):
    edit = bpy.context.preferences.edit
    if edit.use_global_undo and edit.undo_steps >= MIN_UNDO_STEPS:
        return
    if desktop:
        raise failed(
            "Blender's global undo is off or has fewer than 2 steps (Preferences > Editing > Undo); "
            "Blendworks needs it to roll back a failing command"
        )
    edit.use_global_undo = True
    edit.undo_steps = max(edit.undo_steps, MIN_UNDO_STEPS)


def undo_push(message):
    with bpy.context.temp_override(**window_context()):
        bpy.ops.ed.undo_push(message=message)


def undo_back():
    try:
        with bpy.context.temp_override(**window_context()):
            result = bpy.ops.ed.undo()
    except RuntimeError as error:
        raise failed(f"Blender's undo could not roll the scene back: {error}") from error
    if "FINISHED" not in result:
        raise failed("Blender's undo could not roll the scene back")
