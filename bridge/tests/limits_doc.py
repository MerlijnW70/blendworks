"""Writes docs/LIMITS.md from the named limits and the command schemas.

Run: blender -b --factory-startup --python bridge/tests/limits_doc.py
test_world_scale.py checks that the file matches what this writes."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "bridge"))

from blendworks_bridge import commands, limits
from blendworks_bridge.registry import COMMANDS
from blendworks_bridge.schema import bounds

DOC = os.path.join(REPO, "docs", "LIMITS.md")
MACHINE_DEPENDENT = ("scene_memory", "cover_instances")
SHOWN_USES = 6

INTRO = """# Limits

Every bound in a tool schema comes from one named limit of `bridge/blendworks_bridge/limits.py` (the tool families'
limits are defined in `limits_parts.py` and `limits_parts_more.py` and read through it). This table lists
them all, each with the kind of reason and the reason for its value. One quantity has one limit in every tool: a
length is a length in `sweep` and in `atmosphere`. `npm run check` fails when a schema bound has no named limit,
when a bound differs from its limit, or when a limit is missing here (`bridge/tests/test_world_scale.py`); this file
is written by `bridge/tests/limits_doc.py`.

Kinds of reason: **physical** (the range of the quantity in the world), **memory** (what one call may allocate),
**time** (how long one call may run), **blender** (a limit of Blender itself), **protocol** (the request format).

Bounds that define what a field holds are not limits and are not listed: a minimum of 0 (the sign of a quantity),
an integer minimum of 1 (at least one), a non-empty string, a list that may be empty or needs one item, and the
number of items of a tuple of at most four (a vector, a pair, a colour).

## How big a scene can be

- Positions reach 200 km from the origin (`coordinate`), lengths and distances 400 km (`length`), heights and
  displacements 20 km (`relief`). Clip distances, visibility, tile sizes, cloud fields, haze domains, scatter and
  ground-cover regions, liquid bodies and render bounds all use these.
- Counts that cost memory derive from `scene_memory`: half of what the bridge process may use, read when it starts
  from its container's cgroup limit (`memory.max`, or `memory.limit_in_bytes`) or else the physical memory. In the
  judge's 8 GB container that is 4 GB, so `ground_cover` allows 6.7 million instances there and its default of one
  million (640 MB) fits. The two rows below that depend on it show the value on the machine that wrote this file.
- Ask before you build: `validate` checks a whole plan of calls against these limits and the names earlier calls
  make, and lists every problem at once without running anything.

## Precision far from the origin

Blender stores positions as float32: a position p is held to within |p| * 2^-24, 0.5 mm at 16 km and 7.8 mm anywhere
up to 262 km. Two things keep that from showing:
- An object's vertices are stored relative to the object, so a rock, tree or tile keeps its full detail wherever it
  stands; only its placement carries the error above (`test_world_scale.py` places objects 150 km out within 7.9 mm).
- The renderers flatten every mesh into world space in float32, which would round geometry next to a camera at 150 km
  to 15.6 mm. So every render the bridge starts is camera-relative (`floating_origin.py`): when the camera that
  render uses stands farther than `safe_camera_distance` (16 384 m) from the origin horizontally, the world moves by
  the camera's x and y, rounded to whole metres, for that render and every changed value is put back exactly
  afterwards. Every root object, and every root of a collection an object instances, is parented to one temporary
  empty at minus the offset, so animation, drivers, parents and constraints in local or relative spaces evaluate as
  before; Limit Location in world space and Child Of (x and y location on) get offset numbers; instanced collections
  get an offset instance offset; shaders that read the world position (Geometry Position, Vector Transform of a point
  to or from world space) get the offset added back, so clouds, cloud shadows, rain and world-placed textures fall
  where they fall unmoved. Before rendering, every object's evaluated world matrix, every bone's pose and every
  evaluated mesh's bounds are measured against the unmoved scene; settings no moved frame can follow (emitter
  particles, modifiers whose texture reads global coordinates, drivers that read world positions, a constraint such as
  Copy Location with offset in world space) or a failed measurement keep the world in place: that render runs unmoved,
  at plain float32 precision, and the reply names the reason under `camera_relative`. A render without its own camera
  (preview turntables, close-ups) moves only when the camera it uses stands far out. Heights stay, so haze height
  falloff keeps its meaning; a position pass is camera-relative. Not covered: with motion blur the measurement is
  taken at the frame itself, not at every subframe; an instanced collection whose instance offset is not a multiple
  of the float32 step at the moved distance keeps unmoved precision for its instances; drivers on anything but
  transforms that read world positions through other paths are not seen. `test_floating_origin.py` renders a static,
  a keyframed, a Child Of, a driven, a collection-instanced and a world-Limit-Location cube 150 km out moved and
  unmoved, cloud sheets and volumes with their shadows, previews without a camera, and checks exact restore after a
  render and after a failure.
- `heightfield` refuses a tile whose `tile` times `size` would put an edge past the coordinate limit.

## Counts checked before the work

Tools whose work grows with a length, a scale or a count check the count first and refuse before allocating:
`roller_chain` (links from the path length over the pitch), `engrave` and `engrave_scale`, `tree_leaves`, the tree
foliage, `extrude`, `gear`, `sprocket`, `bevel` and the `bevel` and `screw` cases of `add_modifier`. `tree_mesh`
keeps the checks it had: with `lod` the ring density is chosen to meet the budget, the voxel junction estimates its
triangles from the tube area before remeshing, and a skin-joined bark mesh without `lod` has no vertex cap. The estimate of `add_modifier` does not cover a bevel limited by weight or vertex group, nor a
shrinkwrap over a subdivision; those are still refused once the modifier has been evaluated (or applied), against
`mesh_vertices`, and the call is undone.

## Known gaps outside this job

These keep a 10 km figure in code this job may not change; they are left to the jobs that own those files:
- `weather_build.py` (`HAZE_REACH`, 10 km): `weather` only adds haze when the visibility is under 10 km and caps its
  haze there. For landscape haze call `atmosphere` with the visibility you need, as `docs/examples/world_scale.py` does.
- `commands/lights.py`: `add_camera` sets a far clip of 10 km. Set `clip_end` with `camera_setup` (up to `length`).
- `erode`: the brush lists (radius / grid spacing)^2 cells per droplet; the schema cannot see the spacing, so the
  radius keeps its 1 km cap (`erosion_brush`) until `erode` checks the cell count itself.

## Table

| Limit | Value | Unit | Kind | Reason | Instead | Used by |
|---|---|---|---|---|---|---|
"""


def uses():
    found = {}
    for name in sorted(COMMANDS):
        for where, keyword, value, tag in bounds(COMMANDS[name].schema):
            if tag is not None:
                found.setdefault(tag, [])
                entry = f"{name}{where[4:]}"
                if entry not in found[tag]:
                    found[tag].append(entry)
    return found


def value_text(entry):
    if entry["name"] in MACHINE_DEPENDENT:
        return "machine"
    value = entry["value"]
    return f"{value:,}" if isinstance(value, int) else f"{value:g}"


def render():
    commands.load()
    used = uses()
    rows = []
    for entry in limits.table():
        places = used.get(entry["name"], [])
        shown = ", ".join(f"`{place}`" for place in places[:SHOWN_USES])
        if len(places) > SHOWN_USES:
            shown += f" and {len(places) - SHOWN_USES} more"
        cells = [f"`{entry['name']}`", value_text(entry), entry["unit"] or "-", entry["kind"],
                 entry["reason"].replace("|", "/"), entry.get("instead", "-") or "-", shown or "(internal)"]
        rows.append("| " + " | ".join(cells) + " |")
    return INTRO + "\n".join(rows) + "\n"


if __name__ == "__main__":
    with open(DOC, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render())
    print(f"wrote {DOC}")
