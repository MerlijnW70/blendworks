from mathutils import Matrix, Vector

from .errors import bad_args
from .kit_limits import MAX_PATH_POINTS
from .meshdata import MeshData
from .shading import hard_corners
from .shell_profile import normalised_profile
from .shell_rings import Spiral
from .shell_wall import inner_rings
from .skin import cap, skin, skin_between

MAX_GROWTH = 1e5
MIRROR = Matrix.Scale(-1.0, 4, Vector((0.0, 1.0, 0.0)))


def build_spiral(args):
    profile, size = normalised_profile(args)
    ribs, ridges, lip = args.get("ribs"), args.get("spiral_ridges"), args.get("lip")
    if ribs and args["steps"] < 4 * ribs["count"]:
        raise bad_args("steps must be at least 4 per rib so the ribs are resolved")
    if ridges and profile.count < 4 * ridges["count"]:
        raise bad_args("profile_segments must be at least 4 per spiral ridge so the ridges are resolved")
    if args["W"] ** args["turns"] > MAX_GROWTH:
        raise bad_args(f"W to the power turns is above {MAX_GROWTH:.0f}: the apex would be too small to build; lower W or turns")
    if round(args["turns"] * args["steps"]) + 1 > MAX_PATH_POINTS:
        raise bad_args(f"turns times steps is above {MAX_PATH_POINTS}")
    spiral = Spiral(profile, size, args["W"], args["D"], args["T"], args["turns"], args["steps"], ribs, ridges, lip)
    heights = (ribs["height"] if ribs else 0.0) + (ridges["height"] if ridges else 0.0)
    if heights >= spiral.inner:
        raise bad_args("ribs and spiral_ridges together are taller than the gap D leaves to the axis; raise D or lower the heights")
    return spiral


def harden_ring(data, ring):
    for j in range(len(ring)):
        data.harden(ring[j], ring[(j + 1) % len(ring)])


def shell_data(args):
    spiral = build_spiral(args)
    times = spiral.times()
    rings = [spiral.ring(t) for t in times]
    data = MeshData()
    outer = skin(data, rings)
    for corner in hard_corners(spiral.profile.points, True):
        for k in range(len(rings) - 1):
            data.harden(outer[k][corner], outer[k + 1][corner])
    centres = [sum(ring, Vector()) / len(ring) for ring in rings]
    cap(data, outer[0], rings[0], centres[0] - centres[1])
    harden_ring(data, outer[0])
    harden_ring(data, outer[-1])
    info = {"rings": len(rings), "tail_rings": spiral.tail, "points_per_ring": spiral.profile.count, "wall": None, "cavity_from_ring": None}
    thickness = args.get("thickness")
    if thickness is None:
        cap(data, outer[-1], rings[-1], centres[-1] - centres[-2])
    else:
        lip = spiral.lip
        first, inner, wall = inner_rings(spiral, rings, thickness, lambda t: 1.0 + (lip["thicken"] * spiral.lip_factor(t) if lip else 0.0))
        indices = [[data.vertex(point) for point in ring] for ring in inner]
        skin_between(data, indices[::-1], inner[::-1])
        skin_between(data, [outer[-1], indices[-1]], [rings[-1], inner[-1]])
        cap(data, indices[0], inner[0], centres[first + 1] - centres[first])
        harden_ring(data, indices[0])
        harden_ring(data, indices[-1])
        info.update({"wall": wall, "cavity_from_ring": first})
    if args["handedness"] == "left":
        data.transform(MIRROR)
    return data, info
