import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=2.0)
cube = bpy.context.active_object
triangles = sum(len(polygon.vertices) - 2 for polygon in cube.data.polygons)
assert triangles == 12, triangles
assert tuple(round(v, 6) for v in cube.dimensions) == (2.0, 2.0, 2.0), tuple(cube.dimensions)
