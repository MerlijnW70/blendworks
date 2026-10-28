FIXTURE_DEPS = ()
import os
import sys

import bpy

UNC_IMAGE = "\\\\judge-host\\share\\secret.png"


def folders():
    assets = sys.argv[sys.argv.index("--") + 1]
    return os.path.join(assets, "delivery"), os.path.join(assets, "host")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cube():
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    return bpy.context.active_object


def secret_image(host):
    path = os.path.join(host, "secret.png")
    image = bpy.data.images.new("secret", 8, 8)
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return image


def textured_cube(image):
    obj = cube()
    material = bpy.data.materials.new("painted")
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    obj.data.materials.append(material)
    return obj


def save(folder, name, compress=False):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, name), relative_remap=False, compress=compress, copy=True)


def blend_files(folder, host):
    for name, path, compress in (
        ("absolute-image.blend", None, False),
        ("compressed-absolute-image.blend", None, True),
        ("unc-image.blend", UNC_IMAGE, False),
        ("escaping-image.blend", "//../secret.png", False),
    ):
        reset()
        image = secret_image(host)
        if path is not None:
            image.filepath_raw = path
        textured_cube(image)
        save(folder, name, compress)
    reset()
    image = secret_image(host)
    image.pack()
    textured_cube(image)
    save(folder, "packed-image.blend")
    reset()
    cube().name = "shared"
    library = os.path.join(host, "library.blend")
    bpy.ops.wm.save_as_mainfile(filepath=library)
    reset()
    with bpy.data.libraries.load(library, link=True) as (source, target):
        target.objects = ["shared"]
    for obj in target.objects:
        bpy.context.scene.collection.objects.link(obj)
    save(folder, "linked-library.blend")


def fbx_files(folder, host):
    reset()
    textured_cube(secret_image(host))
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "absolute.fbx"), path_mode="ABSOLUTE")
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "escaping.fbx"), path_mode="RELATIVE")
    image = bpy.data.images["secret"]
    image.filepath_raw = os.path.join(folder, "inside.png")
    image.save()
    bpy.ops.export_scene.fbx(filepath=os.path.join(folder, "inside.fbx"), path_mode="RELATIVE")


def main():
    folder, host = folders()
    os.makedirs(folder, exist_ok=True)
    os.makedirs(host, exist_ok=True)
    blend_files(folder, host)
    fbx_files(folder, host)


main()
