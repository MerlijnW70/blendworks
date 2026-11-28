"""River banks shaped by their bends: cut banks and point bars, slumps, stage steps and undercut lips.

Sources (docs/research/bank-form.md):
- Bends: flow is pushed to the outside of a bend, which scours a pool and cuts the outer bank; the inside builds a point
  bar (Leopold and Wolman 1960; Knighton 1998, Fluvial Forms and Processes). Bank erosion is greatest for bends whose radius
  of curvature is about two to three channel widths and fades out above about ten (Hickin and Nanson 1984), so a bend's
  intensity runs from 1 at a radius of BEND_SHARP widths to 0 at BEND_GENTLE.
- Slopes are kept as rise over run: the outer bank face runs from the 1:2 of a straight reach (0.5) to 85 degrees
  (11.43) on the sharpest bend; point bars from 8 degrees (0.14) to 3 degrees (0.052) over
  BAR_WIDTH channel widths, then the accretion bank up to the floodplain at BAR_SCARP (17 degrees).
- Cut banks stand steep to vertical, often undercut below a root-bound top layer of 0.2 to 0.5 m (Thorne 1990); the pool
  is up to about 1.5 times the mean depth. Point bars slope gently, 2 to 8 degrees, towards the channel (Bridge 2003).
- Cut banks fail in slumps and topples whose blocks come to rest at the toe (Thorne 1990); here they occur as a Poisson
  process of SLUMP_RATE per metre of strongly cut bank.
- Banks that are not cut keep the small steps and benches of past water stages, STEP high (Knighton 1998).
"""
import bpy
import numpy

from . import ground_form
from .meshdata import MeshData

BEND_SHARP = 2.0
BEND_GENTLE = 10.0
CUT_SLOPE = (0.5, 11.43)
BAR_SLOPE = (0.14, 0.052)
BAR_WIDTH = 1.0
BAR_SCARP = 0.3
POOL_DEEPEN = 0.5
THALWEG_SHIFT = 0.3
STEP = 0.1
STEP_BAND = 0.6
SLUMP_RATE = 0.12
SLUMP_LENGTH = (0.6, 1.5)
SLUMP_RETREAT = (0.3, 0.8)
SLUMP_BEND = 0.5
LIP_BEND = 0.6
LIP_HEIGHT = 0.3
LIP_THICKNESS = (0.2, 0.45)
LIP_RAGGED = 0.6
LIP_RAGGED_SPAN = 4
LIP_DROOP = 0.35
LIP_RING = 5
LIP_OVERHANG = (0.12, 0.35)
LIP_BACK = 0.35
MUD_BAND = 0.12


def curvature(path, width):
    """Signed curvature of the path (positive turning left), from the cross product of its first and second derivatives,
    averaged over about a channel width."""
    first = numpy.gradient(path.xy, path.s, axis=0)
    second = numpy.gradient(first, path.s, axis=0)
    speed = numpy.maximum(numpy.linalg.norm(first, axis=1), 1e-9)
    kappa = (first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / speed**3
    span = max(int(round(width / max(path.s[1] - path.s[0], 1e-9))), 1)
    kernel = numpy.ones(2 * span + 1) / (2 * span + 1)
    return numpy.convolve(numpy.pad(kappa, span, mode="edge"), kernel, mode="valid")


def bend_intensity(kappa, width):
    """1 where the radius of curvature is at most BEND_SHARP widths, 0 from BEND_GENTLE widths on, linear between."""
    ratio = 1.0 / numpy.maximum(numpy.abs(kappa) * width, 1e-9)
    return numpy.clip((BEND_GENTLE - ratio) / (BEND_GENTLE - BEND_SHARP), 0.0, 1.0)


def blend(pair, share):
    return pair[0] + (pair[1] - pair[0]) * share


def section(distance, outer, bend, level, here, half, ground):
    """The bed and bank height at a distance from the centreline: on the outer side of a bend a deeper pool shifted
    towards the bank and a bank face as steep as the bend is sharp; on the inner side a shallow bed that rises as a point
    bar at a gentle slope past the water's edge; on a straight reach the parabolic bed and 1:2 banks."""
    shift = THALWEG_SHIFT * bend * half
    across = numpy.clip(numpy.where(outer, numpy.abs(distance - shift) / numpy.maximum(half - shift, 1e-9), (distance + shift) / (half + shift)), 0.0, 1.0)
    deep = here * (1.0 + POOL_DEEPEN * bend * outer)
    bed = level - deep * (1.0 - across**2)
    steep = blend(CUT_SLOPE, bend)
    face = level + (distance - half) * numpy.where(outer, steep, 0.5)
    bar_slope = blend(BAR_SLOPE, bend)
    bar_start = half * (1.0 - 0.6 * bend)
    past = distance - bar_start
    rising = level - deep + (distance + shift) * deep / numpy.maximum(bar_start + shift, 1e-9)
    bar = level + numpy.minimum(past, BAR_WIDTH * 2.0 * half) * bar_slope + numpy.maximum(past - BAR_WIDTH * 2.0 * half, 0.0) * BAR_SCARP
    inner = numpy.where(past <= 0.0, rising, bar)
    target = numpy.where(distance <= half, bed, face)
    target = numpy.where((~outer) & (bend > 0.0), inner * bend + target * (1.0 - bend), target)
    return target, steep


def stage_steps(target, level, plain):
    """Benches STEP high on banks that are not cut, within STEP_BAND above the water: a flat tread over three quarters of
    each step and a riser over the rest."""
    rise = target - level
    inside = plain & (rise > 0.0) & (rise < STEP_BAND)
    count = numpy.floor(rise / STEP)
    part = rise / STEP - count
    riser = numpy.clip((part - 0.75) / 0.25, 0.0, 1.0)
    stepped = level + STEP * (count + riser * riser * (3.0 - 2.0 * riser))
    return numpy.where(inside, stepped, target)


def slumps(path, bend, kappa, rng):
    """Slump sites along strongly cut bank: a Poisson number of SLUMP_RATE per metre where the bend intensity passes
    SLUMP_BEND, each at a uniform place with a length and retreat from the stated ranges."""
    cut = bend > SLUMP_BEND
    step = float(path.s[1] - path.s[0])
    length = float(cut.sum()) * step
    count = int(rng.poisson(SLUMP_RATE * length)) if length > 0.0 else 0
    candidates = numpy.nonzero(cut)[0]
    if not count or not len(candidates):
        return []
    picks = rng.choice(candidates, size=count)
    return [{"index": int(i), "length": float(rng.uniform(*SLUMP_LENGTH)), "retreat": float(rng.uniform(*SLUMP_RETREAT))} for i in picks]


def apply_slumps(sites, path, index, distance, outer, ground, target, level, half, steep):
    """Each slump drops the bank top behind the face by about half the bank height over its retreat and length (the
    rotated block) and leaves a heap of debris at the toe above the water."""
    scarred = numpy.zeros(len(target), dtype=bool)
    for site in sites:
        along = numpy.abs(path.s[index] - path.s[site["index"]])
        reach = numpy.clip(1.0 - (along / site["length"]) ** 2, 0.0, 1.0)
        face_top = half + (ground - level) / steep
        behind = outer & (reach > 0.0) & (distance >= face_top - 0.1) & (distance <= face_top + site["retreat"])
        slumped = level + (ground - level) * (1.0 - 0.45 * reach)
        target = numpy.where(behind, numpy.minimum(target, slumped), target)
        toe = outer & (reach > 0.0) & (distance > half - 0.5) & (distance < half + 0.2)
        heap = level + 0.08 + 0.25 * (ground - level) * reach * numpy.clip(1.0 - numpy.abs(distance - half + 0.15) / 0.35, 0.0, 1.0)
        target = numpy.where(toe, numpy.maximum(target, numpy.minimum(heap, ground)), target)
        scarred |= behind | toe
    return target, scarred


def shape(points, path, width, depth, seed):
    """Targets for terrain points beside a river (world xyz rows), the surface class amplitude of each, and the data the
    undercut lip needs."""
    half = width / 2.0
    kappa = curvature(path, width)
    bend_all = bend_intensity(kappa, width)
    index, distance, side = path.nearest(points)
    bend = bend_all[index]
    outer = (side * numpy.sign(kappa[index])) < 0.0
    level = path.level[index]
    here = path.depth[index] if path.depth is not None else numpy.full(len(points), depth)
    ground = points[:, 2]
    target, steep = section(distance, outer & (bend > 0.0), bend, level, here, half, ground)
    target = stage_steps(target, level, ~(outer & (bend > SLUMP_BEND)))
    rng = numpy.random.default_rng([seed, 0xBA4C])
    sites = slumps(path, bend_all, kappa, rng)
    target, scarred = apply_slumps(sites, path, index, distance, outer & (bend > SLUMP_BEND), ground, target, level, half, steep)
    final = numpy.minimum(target, ground)
    rise = final - level
    face = outer & (bend > 0.3) & (distance > half) & (rise > 0.05)
    bar = (~outer) & (bend > 0.2) & (rise > -0.05) & (distance > half * 0.4) & (rise < 0.4)
    amplitude = numpy.full(len(points), ground_form.ROUGHNESS["turf"])
    amplitude = numpy.where(face | scarred, ground_form.ROUGHNESS["soil"], amplitude)
    amplitude = numpy.where(bar, ground_form.ROUGHNESS["gravel"], amplitude)
    amplitude = numpy.where(numpy.abs(rise) < MUD_BAND, ground_form.ROUGHNESS["mud"], amplitude)
    report = {"slumps": len(sites), "cut_bank_length": round(float((bend_all > SLUMP_BEND).sum() * (path.s[1] - path.s[0])), 3),
              "sharpest_bend_radius": round(float(1.0 / max(numpy.abs(kappa).max(), 1e-9)), 3)}
    return final, amplitude, {"kappa": kappa, "bend": bend_all, "steep": steep}, report


def smooth_noise(rng, count, span):
    """count values in 0..1 that wander smoothly: uniform draws averaged over span neighbours, stretched back to 0..1."""
    raw = numpy.convolve(rng.uniform(size=count + 2 * span), numpy.ones(2 * span + 1) / (2 * span + 1), mode="valid")[:count]
    low, high = raw.min(), raw.max()
    return (raw - low) / (high - low) if high > low else numpy.full(count, 0.5)


def lip(ground_objects, path, width, kappa, bend, sample_height, name, seed=0):
    """An undercut lip along the strongly cut stretches: the root-bound top layer of the bank, 0.2 to 0.45 m thick
    (LIP_THICKNESS; Thorne 1990), reaching LIP_OVERHANG past the bank face over the water, as its own closed strip mesh with
    the ground's material. Its edge is ragged where turf blocks have broken away (the reach varies by LIP_RAGGED along it)
    and sags at the tip (LIP_DROOP of the reach), with the underside rounded back into the undercut. A
    stretch where the bank stands less than LIP_HEIGHT above the water has none."""
    half = width / 2.0
    normal = numpy.column_stack([-path.tangent[:, 1], path.tangent[:, 0]])
    outward = -numpy.sign(kappa)[:, None] * normal
    runs, current = [], []
    for i in range(len(path.s)):
        steep = blend(CUT_SLOPE, bend[i])
        ok = bend[i] > LIP_BEND
        if ok:
            top = sample_height(*(path.xy[i] + outward[i] * (half + 1.2)))
            height = (top - path.level[i]) if top is not None else 0.0
            ok = height >= LIP_HEIGHT
        if ok:
            edge = half + height / steep
            overhang = LIP_OVERHANG[0] + (LIP_OVERHANG[1] - LIP_OVERHANG[0]) * (bend[i] - LIP_BEND) / (1.0 - LIP_BEND)
            current.append((path.xy[i], outward[i], edge, top, overhang))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    runs = [run for run in runs if len(run) >= 3]
    if not runs:
        return None
    verts, faces = [], []
    rng = numpy.random.default_rng([seed, 0x11B])
    for run in runs:
        start = len(verts)
        rings = len(run)
        ragged = smooth_noise(rng, rings, LIP_RAGGED_SPAN)
        thick = smooth_noise(rng, rings, LIP_RAGGED_SPAN)
        for k, (xy, out, edge, top, overhang) in enumerate(run):
            reach = overhang * (1.0 - LIP_RAGGED + 2.0 * LIP_RAGGED * ragged[k])
            depth = LIP_THICKNESS[0] + (LIP_THICKNESS[1] - LIP_THICKNESS[0]) * thick[k]
            droop = LIP_DROOP * reach
            for back, lift in ((edge + LIP_BACK, 0.02), (edge - reach, -droop), (edge - reach * 0.85, -droop - 0.5 * depth), (edge + 0.05, -depth), (edge + LIP_BACK, -depth)):
                point = xy + out * back
                verts.append((float(point[0]), float(point[1]), float(top + lift)))
        for k in range(rings - 1):
            a, b = start + LIP_RING * k, start + LIP_RING * (k + 1)
            for j in range(LIP_RING):
                faces.append((a + j, a + (j + 1) % LIP_RING, b + (j + 1) % LIP_RING, b + j))
        faces.append(tuple(start + j for j in range(LIP_RING))[::-1])
        faces.append(tuple(start + LIP_RING * (rings - 1) + j for j in range(LIP_RING)))
    data = MeshData()
    for point in verts:
        data.vertex(point)
    for face in faces:
        data.face(face)
    mesh = bpy.data.meshes.new(name)
    data.to_mesh(mesh)
    source = ground_objects[0]
    for slot in source.material_slots:
        if slot.material is not None:
            mesh.materials.append(slot.material)
            break
    obj = bpy.data.objects.new(name, mesh)
    for collection in source.users_collection:
        collection.objects.link(obj)
    return obj


def mark_relief(obj, rows, amplitude, changed):
    """Store the micro-relief class of the reshaped ground (ground_form.RELIEF_ATTRIBUTE) on the rows it reached, keeping
    the other vertices' values (turf where the ground had none), and flag the object as formed terrain."""
    mesh = obj.data
    values = numpy.full(len(mesh.vertices), ground_form.ROUGHNESS["turf"], dtype=numpy.float32)
    found = mesh.attributes.get(ground_form.RELIEF_ATTRIBUTE)
    if found is not None and found.domain == "POINT":
        found.data.foreach_get("value", values)
    values[rows[changed]] = amplitude[changed]
    ground_form.store_relief(obj, values)
