"""Mesh topology reports: manifold check, Euler characteristic and problems."""

import bmesh


def manifold_report(bm):
    open_edges = sum(1 for edge in bm.edges if len(edge.link_faces) != 2)
    inconsistent = sum(1 for edge in bm.edges if len(edge.link_faces) == 2 and not edge.is_contiguous)
    pinched = sum(1 for vert in bm.verts if vert.link_faces and not vert.is_manifold)
    loose = sum(1 for vert in bm.verts if not vert.link_faces)
    return {
        "manifold": bool(bm.faces) and open_edges == 0 and inconsistent == 0 and pinched == 0 and loose == 0,
        "open_edges": open_edges,
        "inconsistent_edges": inconsistent,
        "pinched_vertices": pinched,
        "loose_vertices": loose,
    }


def euler_characteristic(bm):
    return len(bm.verts) - len(bm.edges) + len(bm.faces)


def mesh_report(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        report = manifold_report(bm)
        report["euler"] = euler_characteristic(bm)
        report["volume"] = bm.calc_volume(signed=True) if report["manifold"] else None
        return report
    finally:
        bm.free()


def describe_problems(report):
    parts = []
    if report["open_edges"]:
        parts.append(f"{report['open_edges']} edge(s) without exactly two faces")
    if report["inconsistent_edges"]:
        parts.append(f"{report['inconsistent_edges']} edge(s) with flipped normals")
    if report["pinched_vertices"]:
        parts.append(f"{report['pinched_vertices']} pinched vertex(es)")
    if report["loose_vertices"]:
        parts.append(f"{report['loose_vertices']} loose vertex(es)")
    return ", ".join(parts) or "no faces"
