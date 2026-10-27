import datetime
import os
import re

import bpy

from .. import limits
from ..autosave import FOLDER
from ..blendfile import open_blend, save_atomically
from ..errors import bad_args, forbidden, not_found
from ..policy import NO_SNAPSHOT, REPLACES_FILE
from ..registry import command
from ..schema import boolean, string

CHECKPOINT_FOLDER = os.path.join(FOLDER, "checkpoints")
CHECKPOINT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DISCARD = boolean("Desktop only: replace the open file even though it has unsaved changes.", False)


def checkpoint_folder(workspace):
    return os.path.join(workspace.root, CHECKPOINT_FOLDER)


def checkpoint_path(workspace, name):
    if not CHECKPOINT_NAME.match(name) or name.endswith("."):
        raise bad_args("a checkpoint name is 1 to 64 letters, digits, _, - or ., starting with a letter or digit")
    return os.path.join(checkpoint_folder(workspace), f"{name}.blend")


def modified_at(path):
    stamp = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def list_checkpoints(workspace):
    folder = checkpoint_folder(workspace)
    if not os.path.isdir(folder):
        return []
    found = []
    for file_name in sorted(os.listdir(folder)):
        name, extension = os.path.splitext(file_name)
        path = os.path.join(folder, file_name)
        if extension == ".blend" and CHECKPOINT_NAME.match(name) and os.path.isfile(path):
            found.append({"name": name, "saved_at": modified_at(path), "bytes": os.path.getsize(path)})
    return found


def ensure_may_replace(ctx, discard):
    if ctx.desktop and bpy.data.is_dirty and not discard:
        raise forbidden("the open file has unsaved changes; save it first, or pass discard_unsaved true")


def opened(ctx, path):
    scene = bpy.context.scene
    return {
        "path": ctx.workspace.relative(path),
        "scene": scene.name,
        "objects": len(scene.objects),
    }


@command(
    "checkpoint",
    "Save the whole scene as a named checkpoint in the workspace, to bring back later with restore_checkpoint.",
    {"name": string("Checkpoint name: letters, digits, _, - and ., at most 64 characters.", max_length=64)},
    ["name"],
    mutates=False,
    slow=True,
    writes_files=True,
    destructive_when="a checkpoint with this name already exists",
    family="files",
    intents=("save a named snapshot before a risky step", "restore point of the scene"),
    nearest=(("save_blend", "for a .blend file you keep"),),
)
def checkpoint(ctx, args):
    path = checkpoint_path(ctx.workspace, args["name"])
    replaced = os.path.isfile(path)
    if not replaced and len(list_checkpoints(ctx.workspace)) >= limits.MAX_CHECKPOINTS:
        raise bad_args(f"there are already {limits.MAX_CHECKPOINTS} checkpoints; reuse a name to replace one")
    size = save_atomically(path)
    return {
        "name": args["name"],
        "path": ctx.workspace.relative(path),
        "bytes": size,
        "replaced": replaced,
        "objects": len(ctx.scene.objects),
    }


@command(
    "restore_checkpoint",
    "Replace the scene with a checkpoint saved earlier; scene_info lists the checkpoints.",
    {"name": string("Checkpoint name.", max_length=64), "discard_unsaved": DISCARD},
    ["name"],
    slow=True,
    destructive=True,
    snapshot=REPLACES_FILE,
    family="files",
    intents=("go back to a saved snapshot", "undo a bad step by loading a named state"),
    nearest=(("load_blend", "to open a .blend file"),),
)
def restore_checkpoint(ctx, args):
    path = checkpoint_path(ctx.workspace, args["name"])
    if not os.path.isfile(path):
        names = ", ".join(entry["name"] for entry in list_checkpoints(ctx.workspace)) or "none yet"
        raise not_found(f"no checkpoint named {args['name']} (checkpoints: {names})")
    ensure_may_replace(ctx, args["discard_unsaved"])
    open_blend(path)
    result = opened(ctx, path)
    result["name"] = args["name"]
    return result


@command(
    "recover",
    "Reload the newest readable autosave of this headless session; the MCP server calls it after a restart.",
    slow=True,
    internal=True,
    snapshot=NO_SNAPSHOT,
    family="scene",
    intents=("reload the autosave after Blender crashed",),
    nearest=(("restore_checkpoint", "to go back to a state you saved by name"),),
)
def recover(ctx, args):
    if ctx.desktop:
        raise forbidden("recover reloads a headless session's autosave; the desktop add-on does not autosave")
    return ctx.handler.autosave.recover()
