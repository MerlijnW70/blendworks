"""Hardened loop normals for sharp edges."""

from mathutils import Vector


def hardened_loop_normals(bm, bevel_faces):
    bevelled = set(bevel_faces)
    bm.normal_update()
    flat_normals = {}
    for face in bm.faces:
        if face in bevelled:
            continue
        for vert in face.verts:
            flat_normals.setdefault(vert, Vector((0.0, 0.0, 0.0)))
            flat_normals[vert] += face.normal
    normals = []
    for face in bm.faces:
        for loop in face.loops:
            if face not in bevelled:
                normals.append(tuple(face.normal))
                continue
            shared = flat_normals.get(loop.vert)
            blended = shared if shared is not None and shared.length > 1e-9 else loop.vert.normal
            normals.append(tuple(blended.normalized()))
    return normals
