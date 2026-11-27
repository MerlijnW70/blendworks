"""Every limit a tool schema uses, each with the reason for its value.

A limit is a number that also knows its name, its unit, the kind of reason behind it and the reason itself. Schema
helpers record the name of each limit they are given, so every bound in a tool schema traces back to one row of the
limits table (docs/LIMITS.md), and one quantity has one limit in every tool.

Kinds of reason:
- physical: the range the quantity has in the world being modelled;
- memory: what one call may allocate;
- time: how long one call may run;
- blender: a limit of Blender itself;
- protocol: a limit of the request format.
"""
from .limit_base import (BLENDER, FloatLimit, INSTEAD, IntLimit, KINDS, LIMITS, MEMORY, PHYSICAL, PROTOCOL, TIME, limit,
                         limit_of, table)

MAX_COORDINATE = limit("coordinate", 200_000.0, "m", PHYSICAL,
                       "A view from a mountain reaches past 100 km; 200 km from the origin holds such a view around a "
                       "camera anywhere near the centre, and float32 still places a point there within 7.8 mm.")
MAX_LENGTH = limit("length", 1_000_000.0, "m", PHYSICAL,
                   "Any distance inside the world (its diagonal is 566 km) and beyond it the longest views and "
                   "visibilities on Earth (near 500 km), with room; cloud fields drift and fade over such distances.")
MAX_RELIEF = limit("relief", 20_000.0, "m", PHYSICAL,
                   "The largest height difference of real land is about 10 km (Mauna Kea from the sea floor, the "
                   "Everest massif); twice that leaves room for exaggerated terrain.")

MAX_MESH_FROM_DATA_VERTICES = limit("mesh_from_data_vertices", 100_000, "vertices", PROTOCOL,
                                    "Vertices sent inline as JSON; larger meshes come in through import.",
                                    "import (a mesh file in the workspace)")
MAX_MESH_FROM_DATA_FACES = limit("mesh_from_data_faces", 200_000, "faces", PROTOCOL,
                                 "Faces sent inline as JSON; larger meshes come in through import.",
                                 "import (a mesh file in the workspace)")
MAX_MESH_VERTICES = limit("mesh_vertices", 2_000_000, "vertices", MEMORY,
                          "One generated mesh stays under about 200 MB with its edges, faces, normals and UVs.")
MAX_CURVE_POINTS = limit("curve_points", 10_000, "points", PROTOCOL, "Curve points sent inline as JSON.")
MAX_TEXT_LENGTH = limit("text_length", 2_000, "characters", MEMORY,
                        "Text objects are built glyph by glyph; a page of text is the most a label needs.")
MAX_NAMES = limit("names", 1_000, "names", PROTOCOL, "Names one call may list; bigger sets go by collection.",
                  "collection (where the tool takes one)")
MAX_PYTHON_SOURCE = limit("python_source", 200_000, "characters", PROTOCOL, "Source of one run_python call.")
MAX_REQUEST_BYTES = limit("request_bytes", 64 * 1024 * 1024, "bytes", PROTOCOL, "One request line on the bridge pipe.")
MAX_LISTED_NAMES = limit("listed_names", 100, "names", PROTOCOL, "Names one reply lists before it summarises.")
MAX_GRAPH_NODES = limit("graph_nodes", 100, "nodes", PROTOCOL, "Nodes one material_nodes call may add.")
MAX_GRAPH_LINKS = limit("graph_links", 300, "links", PROTOCOL, "Links one material_nodes call may add.")

MAX_RENDER_RESOLUTION = limit("preview_resolution", 1024, "px", PROTOCOL,
                              "Previews come back inline as base64; 1024 px keeps a reply under a few MB.",
                              "render_final (writes a file of any size)")
DEFAULT_RENDER_RESOLUTION = 512
MAX_PREVIEW_SAMPLES = limit("preview_samples", 64, "samples", TIME,
                            "A preview answers in seconds on a CPU; final renders take more.", "render_final")
DEFAULT_PREVIEW_SAMPLES = 16
MAX_JPEG_QUALITY = limit("jpeg_quality", 100, "", PHYSICAL, "The JPEG quality scale ends at 100.")
DEFAULT_JPEG_QUALITY = 85
MAX_IMAGE_SIZE = limit("image_size", 8192, "px", MEMORY,
                       "A float RGBA image of 8192 px squared takes 1 GB, the pixel guard.")
MAX_IMAGE_FILE_BYTES = limit("image_file_bytes", 512 * 1024 * 1024, "bytes", MEMORY, "One image file read from disk.")
MAX_TEXTURE_SIZE = limit("texture_size", 8192, "px", MEMORY, "The same pixel guard as image_size.")
MAX_TEXEL_DENSITY = limit("texel_density", 100_000.0, "px/m", PHYSICAL,
                          "0.01 mm per pixel, finer than any texture an asset needs.")
MAX_PIXEL_GUARD_BYTES = limit("pixel_guard_bytes", 1024 * 1024 * 1024, "bytes", MEMORY,
                              "Pixels one call may hold in memory at once.")

MAX_BAKE_SIZE = limit("bake_size", 4096, "px", MEMORY,
                      "Six float channels of 4096 px squared stay near the pixel guard.")
DEFAULT_BAKE_SIZE = 1024
MAX_BAKE_SAMPLES = limit("bake_samples", 1024, "samples", TIME, "Beyond 1024 samples a bake no longer gets cleaner.")
MAX_BAKE_SECONDS = 600.0
BAKE_SECONDS = limit("bake_seconds", MAX_BAKE_SECONDS, "s", TIME, "The longest call the MCP server waits for.")
DEFAULT_BAKE_SECONDS = 100.0
MAX_BAKE_MARGIN = limit("bake_margin", 64, "px", PHYSICAL, "Island margins wider than 64 px only waste the atlas.")

DEFAULT_AUTOSAVE_SECONDS = 30.0
AUTOSAVE_IDLE_SECONDS = 10.0
REPLAY_BUDGET_RATIO = 100.0
REPLAY_BUDGET_FLOOR_SECONDS = 10.0
MAX_REPLAY_SECONDS = 120.0
MAX_JOURNAL_BYTES = 64 * 1024 * 1024
MAX_CHECKPOINTS = limit("checkpoints", 64, "checkpoints", MEMORY, "Saved checkpoints kept on disk per session.")
DEFAULT_SCENE_INFO_LIMIT = 100
MAX_SCENE_INFO_LIMIT = limit("scene_info_page", 1_000, "objects", PROTOCOL, "Objects one scene_info page lists.")

SCENE_MEMORY_SHARE = 0.5
FALLBACK_MEMORY = 8 * 1024 ** 3


def parse_cgroup_limit(text):
    """Bytes of a cgroup memory limit file (v2 memory.max or v1 memory.limit_in_bytes), or None when unlimited."""
    text = (text or "").strip()
    if not text or text == "max":
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if 0 < value < 1 << 60 else None


def physical_memory():
    try:
        import os
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        pass
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("available", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong),
                        ("page_available", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong),
                        ("virtual_available", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]

        status = Status()
        status.length = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total)
    except (AttributeError, OSError):
        pass
    return None


def available_memory(cgroup_files=("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"),
                     physical=physical_memory):
    """The memory this process may use: the tighter of its cgroup limit (a container) and the physical memory."""
    found = []
    for path in cgroup_files:
        try:
            with open(path, encoding="ascii") as handle:
                value = parse_cgroup_limit(handle.read())
        except OSError:
            continue
        if value is not None:
            found.append(value)
    total = physical()
    if total:
        found.append(total)
    return min(found) if found else FALLBACK_MEMORY


def scene_memory(total):
    return int(total * SCENE_MEMORY_SHARE)


MAX_SCENE_MEMORY = limit("scene_memory", scene_memory(available_memory()), "bytes", MEMORY,
                         "Half of the memory this process may use (its container's limit, else the physical memory), "
                         "measured when the bridge starts; the other half stays for Blender, its undo copy and the "
                         "renderer.")
COVER_INSTANCE_BYTES = 640
MAX_COVER_INSTANCES = limit("cover_instances", MAX_SCENE_MEMORY.plain() // COVER_INSTANCE_BYTES, "instances", MEMORY,
                            "scene_memory divided by 640 bytes per ground-cover instance: 92 bytes of stored "
                            "attributes, about 250 bytes of planning arrays and about 300 bytes of render instance.")

FRACTION = limit("fraction", 1.0, "", PHYSICAL, "A share, weight, mix or colour channel runs from 0 to 1.")
TURN = limit("turn", 360.0, "deg", PHYSICAL, "One full turn; more repeats the same orientation.")
HALF_TURN = limit("half_turn", 180.0, "deg", PHYSICAL, "Angles between two directions run from 0 to 180 degrees.")
QUARTER_TURN = limit("quarter_turn", 90.0, "deg", PHYSICAL,
                     "Slopes, elevations and tilts from a plane run up to 90 degrees.")
MAX_SEED = limit("seed", 2_147_483_647, "", BLENDER, "Blender's random seeds are signed 32-bit integers.")
NAME_LENGTH = limit("name_length", 255, "bytes", BLENDER,
                    "Blender 5.2 keeps datablock names (objects, materials, images, collections, actions) up to 255 "
                    "bytes and cuts longer ones, which would then no longer match.")

MAX_PROBLEMS = limit("problems", 50, "problems", PROTOCOL,
                     "Problems one call reports, at most about 2 KB each, so a refusal stays near 100 KB however bad "
                     "the input; the rest are counted as 'and N more'.", "fix the problems listed, then check again")
MAX_PLAN_PROBLEMS = limit("plan_problems", 500, "problems", PROTOCOL,
                          "Problems one validate answer lists, about 1 MB at most, well inside the MCP line link; the "
                          "rest are counted.", "validate the plan in parts")
SAFE_CAMERA_DISTANCE = limit("safe_camera_distance", 16_384.0, "m", BLENDER,
                             "Renders flatten meshes into float32 world space; within 16 384 m of the origin that keeps "
                             "every point within 0.5 mm. A render whose camera stands farther out moves the world so the "
                             "camera sits near the origin (floating_origin.py).")
MAX_RAMP_STOPS = limit("ramp_stops", 32, "stops", BLENDER, "Blender's colour ramp holds at most 32 stops (MAXCOLORBAND).")
MAX_PLAN_CALLS = limit("plan_calls", 10_000, "calls", TIME,
                       "validate checks each call's schema and names in about a millisecond; 10 000 calls answer within "
                       "seconds, and a larger plan is checked in parts.", "validate the plan in parts")
HEIGHT_BAND = limit("height_band", 1_000_000.0, "m", PHYSICAL,
                    "A height mask only selects points; callers write far ends up to 1000 km to mean no bound, past any "
                    "height the world holds.")
JITTER_SCALE = limit("jitter_scale", 0.99, "", PHYSICAL,
                     "A random scale change as a share either way; below 1 so that no organ shrinks to nothing.")
LEAST_CARD_WIDTH = limit("least_card_width", 0.02, "", PHYSICAL,
                         "A leaf card at least 2 % as wide as it is long; narrower cards vanish edge-on (pine needles "
                         "use about 3 %).")
MIN_MATERIAL_OFFSET = limit("material_offset_min", -32_768, "slots", BLENDER,
                            "Blender's solidify material offset is a signed 16-bit number and starts at -32 768.")


def _gather(*modules):
    """The limits of every tool family, defined in their own modules, are names of this module too."""
    for module in modules:
        globals().update({name: value for name, value in vars(module).items() if name.isupper()})


from . import limits_parts, limits_parts_more

_gather(limits_parts, limits_parts_more)
