import bpy

TRACKED_COLLECTIONS = (
    "objects",
    "meshes",
    "curves",
    "materials",
    "lights",
    "cameras",
    "images",
    "worlds",
    "collections",
    "fonts",
    "node_groups",
    "textures",
)


class ObjectState:
    def __init__(self, obj, view_layer):
        self.obj = obj
        self.name = obj.name
        self.data = obj.data
        self.parent = obj.parent
        self.matrix_basis = obj.matrix_basis.copy()
        self.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
        self.modifiers = [modifier.name for modifier in obj.modifiers]
        self.hide_viewport = obj.hide_viewport
        self.hide_render = obj.hide_render
        in_layer = obj.name in view_layer.objects
        self.hidden = obj.hide_get(view_layer=view_layer) if in_layer else None
        self.selected = obj.select_get(view_layer=view_layer) if in_layer else None

    def restore(self, view_layer):
        obj = self.obj
        if obj.name != self.name:
            obj.name = self.name
        if obj.data != self.data:
            obj.data = self.data
        if obj.parent != self.parent:
            obj.parent = self.parent
        obj.matrix_parent_inverse = self.matrix_parent_inverse
        obj.matrix_basis = self.matrix_basis
        for modifier in list(obj.modifiers):
            if modifier.name not in self.modifiers:
                obj.modifiers.remove(modifier)
        obj.hide_viewport = self.hide_viewport
        obj.hide_render = self.hide_render
        if self.hidden is not None and obj.name in view_layer.objects:
            obj.hide_set(self.hidden, view_layer=view_layer)
            obj.select_set(self.selected, view_layer=view_layer)


class Transaction:
    def __init__(self, scene, view_layer):
        self.scene = scene
        self.view_layer = view_layer
        self.before = {name: {block.as_pointer() for block in getattr(bpy.data, name)} for name in TRACKED_COLLECTIONS}
        self.objects = [ObjectState(obj, view_layer) for obj in scene.objects]
        self.camera = scene.camera
        self.world = scene.world
        self.cursor = scene.cursor.location.copy()
        self.active = view_layer.objects.active
        self.mesh_copies = []
        self.material_values = []
        self.material_copies = []
        self.restores = []
        self.keep = set()

    def touch_mesh(self, mesh):
        for original, _ in self.mesh_copies:
            if original == mesh:
                return
        saved = mesh.copy()
        self.keep.add(saved.as_pointer())
        self.mesh_copies.append((mesh, saved))

    def touch_all_meshes(self):
        for mesh in list(bpy.data.meshes):
            if mesh.as_pointer() not in self.keep:
                self.touch_mesh(mesh)

    def touch_material(self, material, restore):
        self.material_values.append((material, restore))

    def touch_material_tree(self, material):
        if material.as_pointer() not in self.before["materials"]:
            return
        for original, _ in self.material_copies:
            if original == material:
                return
        saved = material.copy()
        saved.use_fake_user = material.use_fake_user
        self.keep.add(saved.as_pointer())
        self.material_copies.append((material, saved))

    def on_rollback(self, restore):
        self.restores.append(restore)

    def commit(self):
        for _, saved in self.mesh_copies:
            bpy.data.meshes.remove(saved)
        for _, saved in self.material_copies:
            bpy.data.materials.remove(saved)
        self.mesh_copies = []
        self.material_values = []
        self.material_copies = []
        self.restores = []

    def rollback(self):
        for state in self.objects:
            try:
                state.restore(self.view_layer)
            except ReferenceError:
                pass
        for original, saved in self.mesh_copies:
            name = original.name
            original.user_remap(saved)
            bpy.data.meshes.remove(original)
            saved.name = name
        self.mesh_copies = []
        for material, restore in reversed(self.material_values):
            restore(material)
        self.material_values = []
        for original, saved in self.material_copies:
            name = original.name
            original.user_remap(saved)
            bpy.data.materials.remove(original)
            saved.name = name
        self.material_copies = []
        for restore in reversed(self.restores):
            restore()
        self.restores = []
        self.remove_new_blocks()
        self.scene.camera = alive(self.camera)
        self.scene.world = alive(self.world)
        self.scene.cursor.location = self.cursor
        self.view_layer.objects.active = alive(self.active)
        self.view_layer.update()

    def remove_new_blocks(self):
        for name in TRACKED_COLLECTIONS:
            collection = getattr(bpy.data, name)
            known = self.before[name] | self.keep
            for block in [block for block in collection if block.as_pointer() not in known]:
                collection.remove(block, do_unlink=True)


def alive(block):
    if block is None:
        return None
    try:
        block.name
    except ReferenceError:
        return None
    return block
