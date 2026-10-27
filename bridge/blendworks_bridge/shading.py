import math

SHADING = ("auto", "smooth", "flat")


def apply_shading(bm, mode, angle_degrees):
    if mode == "flat":
        for face in bm.faces:
            face.smooth = False
        for edge in bm.edges:
            edge.smooth = True
        return
    threshold = math.radians(angle_degrees)
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        if mode == "smooth" or len(edge.link_faces) != 2:
            edge.smooth = True
        else:
            edge.smooth = edge.calc_face_angle(0.0) <= threshold
