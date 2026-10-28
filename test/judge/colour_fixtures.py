FIXTURE_DEPS = ()
import os
import sys

import bpy


def arguments():
    rest = sys.argv[sys.argv.index("--") + 1 :]
    return rest[0]


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cube(name, location, colours=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    if colours is not None:
        domain, data_type = colours
        attribute = obj.data.color_attributes.new("Paint", data_type, domain)
        for index, element in enumerate(attribute.data):
            element.color = ((index % 3) / 2, (index % 5) / 4, (index % 7) / 6, 1.0)
        obj.data.color_attributes.active_color = attribute
    return obj


def export_glb(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_vertex_color="ACTIVE", export_active_vertex_color_when_no_material=True)


def save_blend(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)


def main():
    folder = arguments()
    os.makedirs(folder, exist_ok=True)
    reset()
    cube("Painted", (0.0, 0.0, 0.5), ("CORNER", "BYTE_COLOR"))
    cube("Trim", (1.5, 0.0, 0.5), ("CORNER", "BYTE_COLOR"))
    export_glb(os.path.join(folder, "painted.glb"))
    reset()
    cube("Painted", (0.0, 0.0, 0.5), ("CORNER", "BYTE_COLOR"))
    cube("Trim", (1.5, 0.0, 0.5))
    export_glb(os.path.join(folder, "painted-partly.glb"))
    reset()
    cube("Painted", (0.0, 0.0, 0.5), ("POINT", "FLOAT_COLOR"))
    cube("Trim", (1.5, 0.0, 0.5), ("POINT", "FLOAT_COLOR"))
    save_blend(os.path.join(folder, "painted-points.blend"))


main()
