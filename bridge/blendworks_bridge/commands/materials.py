import bpy

from ..errors import bad_args, not_found
from ..materials_info import PRINCIPLED_INPUTS, material_summary, principled_node
from ..registry import command
from ..schema import color, number, string
from ..selection import FACE_PROPERTIES, select_faces
from ..util import EditMesh, get_object

DEFAULTS = {
    "base_color": [0.8, 0.8, 0.8, 1.0],
    "metallic": 0.0,
    "roughness": 0.5,
    "emission_color": [0.0, 0.0, 0.0],
    "emission_strength": 0.0,
    "alpha": 1.0,
}


@command(
    "add_material",
    "Create a Principled BSDF material, or update the given values of an existing one.",
    {
        "name": string("Material name."),
        "base_color": color("Base colour, linear RGB or RGBA from 0 to 1 (default 0.8 grey)."),
        "metallic": number("Metallic, 0 to 1 (default 0).", 0.0, 1.0),
        "roughness": number("Roughness, 0 to 1 (default 0.5).", 0.0, 1.0),
        "emission_color": color("Emission colour, linear RGB from 0 to 1 (default black).", allow_alpha=False),
        "emission_strength": number("Emission strength (default 0).", 0.0, 1000.0),
        "alpha": number("Opacity, 0 to 1 (default 1).", 0.0, 1.0),
    },
    ["name"],
)
def add_material(ctx, args):
    material = bpy.data.materials.get(args["name"])
    created = material is None
    if created:
        material = bpy.data.materials.new(args["name"])
        material.use_fake_user = True
        values = {key: args.get(key, default) for key, default in DEFAULTS.items()}
    else:
        values = {key: args[key] for key in DEFAULTS if key in args}
    node = principled_node(material)
    if node is None:
        raise bad_args(f"{material.name} has no Principled BSDF node to set")
    for key, value in values.items():
        socket = node.inputs[PRINCIPLED_INPUTS[key]]
        if key == "base_color":
            value = list(value) + [1.0] * (4 - len(value))
            material.diffuse_color = value
        elif key == "emission_color":
            value = list(value) + [1.0]
        socket.default_value = value
    if "alpha" in values:
        material.surface_render_method = "DITHERED"
    summary = material_summary(material)
    summary["created"] = created
    return summary


@command(
    "assign_material",
    "Give an object a material: the whole object, or only the selected faces of a mesh.",
    dict({"name": string("Object."), "material": string("Material name.")}, **FACE_PROPERTIES),
    ["name", "material"],
)
def assign_material(ctx, args):
    obj = get_object(args["name"])
    material = bpy.data.materials.get(args["material"])
    if material is None:
        raise not_found(f"no material named {args['material']}; create it with add_material")
    if obj.type not in ("MESH", "CURVE", "FONT"):
        raise bad_args(f"{obj.name} is a {obj.type.lower()} and cannot hold materials")
    partial = "faces" in args or "facing" in args
    if partial and obj.type != "MESH":
        raise bad_args("faces and facing work only on meshes")
    if not partial:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        if obj.type == "MESH":
            for polygon in obj.data.polygons:
                polygon.material_index = 0
        return {"name": obj.name, "material": material.name, "faces": len(getattr(obj.data, "polygons", []))}
    slots = [slot for slot in obj.data.materials]
    if material.name not in [slot.name for slot in slots if slot is not None]:
        obj.data.materials.append(material)
    index = [slot.name if slot else None for slot in obj.data.materials].index(material.name)
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        for face in faces:
            face.material_index = index
    return {"name": obj.name, "material": material.name, "slot": index, "faces": len(faces)}


@command(
    "vertex_colors",
    "Paint a colour into a mesh's colour attribute, on all faces or the selected ones.",
    dict(
        {
            "name": string("Mesh object."),
            "color": color("Colour, RGB or RGBA from 0 to 1."),
            "layer": string("Colour attribute name; created (white) when missing.", default="Color"),
        },
        **FACE_PROPERTIES,
    ),
    ["name", "color"],
)
def vertex_colors(ctx, args):
    obj = get_object(args["name"])
    if obj.type != "MESH":
        raise bad_args(f"{obj.name} is not a mesh")
    existing = obj.data.color_attributes.get(args["layer"])
    if existing is not None and (existing.domain != "CORNER" or existing.data_type != "BYTE_COLOR"):
        raise bad_args(f"{args['layer']} exists but is not a face-corner byte colour attribute")
    rgba = list(args["color"]) + [1.0] * (4 - len(args["color"]))
    with EditMesh(obj) as bm:
        faces = select_faces(bm, obj, args)
        layer = bm.loops.layers.color.get(args["layer"])
        if layer is None:
            layer = bm.loops.layers.color.new(args["layer"])
            for face in bm.faces:
                for loop in face.loops:
                    loop[layer] = (1.0, 1.0, 1.0, 1.0)
        for face in faces:
            for loop in face.loops:
                loop[layer] = rgba
    attributes = obj.data.color_attributes
    attributes.active_color = attributes[args["layer"]]
    attributes.render_color_index = attributes.find(args["layer"])
    return {"name": obj.name, "layer": args["layer"], "faces": len(faces)}
