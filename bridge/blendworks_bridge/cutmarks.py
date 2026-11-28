"""Marks the edges of a cut so later steps can find the engraved or booleaned faces."""

import bmesh

CUT_ATTRIBUTE = "blendworks_cut"
SHARP_COSINE = 0.866


def mark_cutter(mesh):
    marker = mesh.attributes.get(CUT_ATTRIBUTE) or mesh.attributes.new(CUT_ATTRIBUTE, "INT", "FACE")
    marker.data.foreach_set("value", [1] * len(mesh.polygons))


def unmark(mesh):
    marker = mesh.attributes.get(CUT_ATTRIBUTE)
    if marker is not None:
        mesh.attributes.remove(marker)


def mark_cut_edges(target, engraved=True):
    mesh = target.data
    marker = mesh.attributes.get(CUT_ATTRIBUTE)
    if marker is None:
        return 0
    flags = [0] * len(mesh.polygons)
    marker.data.foreach_get("value", flags)
    mesh.attributes.remove(marker)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        sharp = 0
        for face in bm.faces if engraved else ():
            if flags[face.index]:
                face.smooth = False
        for edge in bm.edges:
            faces = edge.link_faces
            if len(faces) != 2 or not (flags[faces[0].index] or flags[faces[1].index]):
                continue
            bent = faces[0].normal.dot(faces[1].normal) < SHARP_COSINE
            if bent or (engraved and flags[faces[0].index] != flags[faces[1].index]):
                edge.smooth = False
                sharp += 1
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return sharp
