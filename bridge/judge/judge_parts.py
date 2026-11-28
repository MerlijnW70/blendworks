"""Connected components and overlaps of an asset's parts."""

from math import inf

import bmesh

from judge_common import rounded
from judge_shells import DisjointSet

MAX_LISTED = 64
LABEL_LENGTH = 120


def components(graph):
    parts = DisjointSet(len(graph.verts))
    for edge in graph.edges:
        parts.union(edge.verts[0].index, edge.verts[1].index)
    return [parts.find(index) for index in range(len(graph.verts))]


def overlaps(first, second, tolerance):
    return all(first[0][axis] - tolerance <= second[1][axis] and second[0][axis] <= first[1][axis] + tolerance for axis in range(3))


class PartCollector:
    def __init__(self, tolerance, weld_distance):
        self.tolerance = tolerance
        self.weld_distance = weld_distance
        self.parts = []
        self.objects = {}
        self.label_uses = {}

    def label_for(self, key):
        uses = self.label_uses.get(key, 0) + 1
        self.label_uses[key] = uses
        label = key if uses == 1 else f"{key}#{uses}"
        return label[:LABEL_LENGTH]

    def add(self, key, mesh, matrix):
        label = self.label_for(key)
        rows = [tuple(matrix[axis]) for axis in range(3)]
        graph = bmesh.new()
        try:
            graph.from_mesh(mesh)
            bmesh.ops.remove_doubles(graph, verts=graph.verts[:], dist=self.weld_distance)
            graph.verts.index_update()
            roots = components(graph)
            boxes = {}
            for vertex, root in zip(graph.verts, roots):
                x, y, z = vertex.co
                point = [row[0] * x + row[1] * y + row[2] * z + row[3] for row in rows]
                box = boxes.get(root)
                if box is None:
                    boxes[root] = (list(point), list(point))
                    continue
                for axis in range(3):
                    if point[axis] < box[0][axis]:
                        box[0][axis] = point[axis]
                    if point[axis] > box[1][axis]:
                        box[1][axis] = point[axis]
        finally:
            graph.free()
        ordered = sorted(boxes.values(), key=lambda box: (tuple(box[0]), tuple(box[1])))
        low = [inf, inf, inf]
        high = [-inf, -inf, -inf]
        for index, box in enumerate(ordered):
            self.parts.append({"object": label, "index": index, "box": box})
            for axis in range(3):
                low[axis] = min(low[axis], box[0][axis])
                high[axis] = max(high[axis], box[1][axis])
        if ordered:
            self.objects[label] = (low, high)

    def touching(self):
        entries = [(part["box"], part["object"], position) for position, part in enumerate(self.parts)]
        entries += [(box, label, None) for label, box in self.objects.items()]
        entries.sort(key=lambda entry: entry[0][0][0])
        touched = set()
        for first_index, (first_box, first_object, first_part) in enumerate(entries):
            reach = first_box[1][0] + self.tolerance
            for second_box, second_object, second_part in entries[first_index + 1 :]:
                if second_box[0][0] > reach:
                    break
                if first_part is None and second_part is None:
                    continue
                same_object = first_object == second_object
                if same_object and (first_part is None or second_part is None):
                    continue
                if not same_object and first_part is not None and second_part is not None:
                    continue
                if not overlaps(first_box, second_box, self.tolerance):
                    continue
                for part in (first_part, second_part):
                    if part is not None:
                        touched.add(part)
        return touched

    def result(self):
        touched = self.touching() if len(self.parts) > 1 else set(range(len(self.parts)))
        floating = [part for position, part in enumerate(self.parts) if position not in touched]
        floating.sort(key=lambda part: (part["object"], part["index"]))
        return {
            "tolerance": self.tolerance,
            "parts": len(self.parts),
            "count": len(floating),
            "items": [
                {"object": part["object"], "index": part["index"], "bounds": {"min": rounded(part["box"][0]), "max": rounded(part["box"][1])}}
                for part in floating[:MAX_LISTED]
            ],
        }
