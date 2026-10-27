from ..cleaning import clean_bmesh
from ..errors import failed
from ..registry import command
from ..schema import length, number, string
from ..topology import manifold_report
from ..util import EditMesh, get_mesh_object, mesh_counts, rounded
from .mesh_edit import local_length

DEFAULT_TOLERANCE = 0.000001
DEFAULT_MERGE_DISTANCE = 0.00001


def clean_object(obj, tolerance=DEFAULT_TOLERANCE, merge_distance=DEFAULT_MERGE_DISTANCE):
    local_tolerance = local_length(obj, tolerance)
    local_merge = local_length(obj, merge_distance) if merge_distance > 0 else 0.0
    with EditMesh(obj) as bm:
        report, was_closed, is_closed = clean_bmesh(bm, local_tolerance, local_merge)
        if was_closed and not is_closed:
            raise failed(f"cleaning {obj.name} would leave a closed mesh open: {manifold_report(bm)}")
        report["manifold"] = is_closed
        report["volume"] = rounded(bm.calc_volume(signed=True), 9) if is_closed else None
    report["mesh"] = mesh_counts(obj.data)
    return report


@command(
    "clean_mesh",
    "Repair a mesh after booleans: merge close vertices, dissolve degenerate faces, retriangulate sliver polygons, drop collinear vertices and loose geometry, fix normals; reports each count.",
    {
        "name": string("Mesh object."),
        "tolerance": length("Distance in metres under which a triangle's height or a vertex's offset from a straight edge counts as zero.", DEFAULT_TOLERANCE, 0.01),
        "merge_distance": number("Merge vertices closer than this many metres; 0 skips merging.", 0.0, 1.0, DEFAULT_MERGE_DISTANCE),
    },
    ["name"],
    slow=True,
)
def clean_mesh(ctx, args):
    obj = get_mesh_object(args["name"])
    report = clean_object(obj, args["tolerance"], args["merge_distance"])
    report["name"] = obj.name
    return report
