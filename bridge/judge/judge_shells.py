"""Mesh shell analysis: disjoint sets, edge defects and volume."""

import bmesh

FLAT_VOLUME_RATIO = 1e-9


class DisjointSet:
    def __init__(self, size):
        self.parent = list(range(size))

    def find(self, index):
        parent = self.parent
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(self, first, second):
        first = self.find(first)
        second = self.find(second)
        if first != second:
            self.parent[first] = second


def empty_topology():
    return {"nonManifoldEdges": 0, "boundaryEdges": 0, "wireEdges": 0, "nonManifoldVertices": 0, "looseVertices": 0, "looseParts": 0}


def edge_defects(graph, topology):
    for edge in graph.edges:
        faces = len(edge.link_faces)
        if faces == 0:
            topology["wireEdges"] += 1
        elif faces == 1:
            topology["boundaryEdges"] += 1
        elif faces > 2 or not edge.is_contiguous:
            topology["nonManifoldEdges"] += 1
    for vertex in graph.verts:
        if not vertex.link_edges:
            topology["looseVertices"] += 1
        elif not vertex.is_manifold and not vertex.is_boundary and not vertex.is_wire and all(edge.is_manifold and edge.is_contiguous for edge in vertex.link_edges):
            topology["nonManifoldVertices"] += 1


def vertex_parts(graph):
    parts = DisjointSet(len(graph.verts))
    for edge in graph.edges:
        parts.union(edge.verts[0].index, edge.verts[1].index)
    return len({parts.find(index) for index in range(len(graph.verts))})


def face_shells(graph, hidden_slots=frozenset()):
    shells = DisjointSet(len(graph.faces))
    for edge in graph.edges:
        linked = [face for face in edge.link_faces if face.material_index not in hidden_slots]
        for face in linked[1:]:
            shells.union(linked[0].index, face.index)
    members = {}
    for face in graph.faces:
        if face.material_index not in hidden_slots:
            members.setdefault(shells.find(face.index), []).append(face)
    return list(members.values())


def is_closed(faces, hidden_slots=frozenset()):
    for face in faces:
        for edge in face.edges:
            if len(edge.link_faces) != 2 or not edge.is_contiguous:
                return False
            if hidden_slots and any(other.material_index in hidden_slots for other in edge.link_faces):
                return False
    return True


def signed_volume(faces):
    volume = 0.0
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for face in faces:
        points = [vertex.co for vertex in face.verts]
        for point in points:
            for axis in range(3):
                low[axis] = min(low[axis], point[axis])
                high[axis] = max(high[axis], point[axis])
        anchor = points[0]
        for second, third in zip(points[1:], points[2:]):
            volume += anchor.dot(second.cross(third)) / 6.0
    extent = max(high[axis] - low[axis] for axis in range(3))
    return volume, extent


def mesh_topology(mesh, weld_distance, hidden_slots=frozenset()):
    topology = empty_topology()
    shells = {"count": 0, "closed": 0, "inverted": 0}
    graph = bmesh.new()
    try:
        graph.from_mesh(mesh)
        bmesh.ops.remove_doubles(graph, verts=graph.verts[:], dist=weld_distance)
        graph.verts.index_update()
        graph.faces.index_update()
        edge_defects(graph, topology)
        topology["looseParts"] = vertex_parts(graph)
        for faces in face_shells(graph, hidden_slots):
            shells["count"] += 1
            if not is_closed(faces, hidden_slots):
                continue
            shells["closed"] += 1
            volume, extent = signed_volume(faces)
            if volume < -FLAT_VOLUME_RATIO * extent**3:
                shells["inverted"] += 1
    finally:
        graph.free()
    return topology, shells
