import numpy

from .tree_frames import first_normal, sample_tangents, transported_normals

CARD_WIDTH = 2.0


def twig_cards(skeleton, twigs):
    points = []
    corners = []
    uvs = []
    count = 0
    for twig in twigs:
        centres = skeleton.positions[twig.nodes].astype(float)
        radii = skeleton.radii[twig.nodes].astype(float)
        radii[0] = radii[1] if len(radii) > 1 else radii[0]
        tangents = sample_tangents(centres)
        normals = transported_normals(centres, tangents, first_normal(tangents[0]))
        binormals = numpy.cross(tangents, normals)
        along = numpy.concatenate([[0.0], numpy.cumsum(numpy.linalg.norm(numpy.diff(centres, axis=0), axis=1))])
        for across in (normals, binormals):
            half = (CARD_WIDTH * 0.5 * radii)[:, None] * across
            left = centres - half
            right = centres + half
            rows = len(centres)
            block = numpy.empty((2 * rows, 3))
            block[0::2] = left
            block[1::2] = right
            points.append(block)
            for row in range(rows - 1):
                a = count + 2 * row
                corners.append([a, a + 1, a + 3, a + 2])
                width = (CARD_WIDTH * radii[row], CARD_WIDTH * radii[row + 1])
                uvs.append([[0.0, along[row]], [width[0], along[row]], [width[1], along[row + 1]], [0.0, along[row + 1]]])
            count += 2 * rows
    if not points:
        return None
    return numpy.vstack(points), numpy.array(corners, dtype=numpy.int64), numpy.array(uvs, dtype=float)
