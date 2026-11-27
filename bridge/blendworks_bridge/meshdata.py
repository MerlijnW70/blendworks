from mathutils import Vector

from .edge_order import canonical_edges
from .errors import bad_args


class MeshData:
    def __init__(self):
        self.verts = []
        self.faces = []
        self.uvs = []
        self.islands = []
        self.materials = []
        self.smooth = []
        self.edges = []
        self.sharp = set()
        self.creases = {}

    def vertex(self, co):
        self.verts.append(Vector(co))
        return len(self.verts) - 1

    def face(self, indices, uvs=None, island=0, material=0, smooth=False):
        indices = tuple(indices)
        self.faces.append(indices)
        self.uvs.append(list(uvs) if uvs is not None else None)
        self.islands.append(island)
        self.materials.append(material)
        self.smooth.append(smooth)
        return len(self.faces) - 1

    def harden(self, a, b):
        self.sharp.add((min(a, b), max(a, b)))

    def island_count(self):
        return max(self.islands) + 1 if self.islands else 0

    def append(self, other, matrix=None):
        offset = len(self.verts)
        island_offset = self.island_count()
        mirrored = matrix is not None and matrix.to_3x3().determinant() < 0
        if matrix is None:
            self.verts.extend(co.copy() for co in other.verts)
        else:
            self.verts.extend(matrix @ co for co in other.verts)
        for indices, uvs, island, material, smooth in zip(other.faces, other.uvs, other.islands, other.materials, other.smooth):
            shifted = [index + offset for index in indices]
            if mirrored:
                shifted.reverse()
                uvs = list(reversed(uvs)) if uvs is not None else None
            self.face(shifted, uvs, island + island_offset, material, smooth)
        self.edges.extend((a + offset, b + offset) for a, b in other.edges)
        self.sharp.update((a + offset, b + offset) if a < b else (b + offset, a + offset) for a, b in other.sharp)
        self.creases.update({(a + offset, b + offset): value for (a, b), value in other.creases.items()})
        return self

    def transform(self, matrix):
        self.verts = [matrix @ co for co in self.verts]
        if matrix.to_3x3().determinant() < 0:
            self.faces = [tuple(reversed(indices)) for indices in self.faces]
            self.uvs = [list(reversed(uvs)) if uvs is not None else None for uvs in self.uvs]
        return self

    def copy(self):
        return MeshData().append(self)

    @classmethod
    def from_mesh(cls, mesh, uv_layer=None):
        data = cls()
        data.verts = [vertex.co.copy() for vertex in mesh.vertices]
        layer = uv_layer if uv_layer is not None else mesh.uv_layers.active
        for polygon in mesh.polygons:
            data.faces.append(tuple(polygon.vertices))
            if layer is not None:
                data.uvs.append([tuple(layer.uv[index].vector) for index in polygon.loop_indices])
            else:
                data.uvs.append(None)
            data.islands.append(0)
            data.materials.append(polygon.material_index)
            data.smooth.append(polygon.use_smooth)
        loose = [tuple(edge.vertices) for edge in mesh.edges if edge.is_loose]
        data.edges = loose
        data.sharp = {tuple(sorted(edge.vertices)) for edge in mesh.edges if edge.use_edge_sharp}
        return data

    def to_mesh(self, mesh, uv_name="UVMap"):
        mesh.clear_geometry()
        mesh.from_pydata([tuple(co) for co in self.verts], self.edges, self.faces)
        corrected = mesh.validate(verbose=False)
        canonical_edges(mesh)
        intact = len(mesh.polygons) == len(self.faces) and len(mesh.loops) == sum(len(face) for face in self.faces)
        if not intact and self.has_face_data():
            raise bad_args("the faces were invalid (for example duplicate faces), so their UVs, materials and flags cannot be kept; fix the mesh data")
        if self.faces and intact:
            self.write_faces(mesh, uv_name)
        self.write_edges(mesh)
        mesh.update()
        return corrected

    def has_face_data(self):
        return any(uvs is not None for uvs in self.uvs) or any(self.materials) or any(self.smooth)

    def write_faces(self, mesh, uv_name):
        if any(uvs is not None for uvs in self.uvs):
            layer = mesh.uv_layers.new(name=uv_name)
            blank = (0.0, 0.0)
            flat = []
            for indices, uvs in zip(self.faces, self.uvs):
                for uv in uvs if uvs is not None else [blank] * len(indices):
                    flat.extend(uv)
            layer.uv.foreach_set("vector", flat)
        mesh.polygons.foreach_set("material_index", self.materials)
        mesh.polygons.foreach_set("use_smooth", self.smooth)

    def write_edges(self, mesh):
        if not self.sharp and not self.creases:
            return
        flat = [0] * (2 * len(mesh.edges))
        mesh.edges.foreach_get("vertices", flat)
        keys = [(min(flat[2 * i], flat[2 * i + 1]), max(flat[2 * i], flat[2 * i + 1])) for i in range(len(mesh.edges))]
        missing = sorted((set(self.sharp) | set(self.creases)) - set(keys))
        if missing:
            raise bad_args(f"the edge between vertices {missing[0][0]} and {missing[0][1]} does not exist")
        if self.sharp:
            mesh.edges.foreach_set("use_edge_sharp", [key in self.sharp for key in keys])
        if self.creases:
            mesh.edge_creases_ensure()
            layer = mesh.attributes["crease_edge"]
            layer.data.foreach_set("value", [self.creases.get(key, 0.0) for key in keys])

