import math

import bpy

from .errors import bad_args, not_found
from .limits import (BEVEL_SEGMENTS, FEWEST_SPLIT_CORNERS, FRACTION, HALF_TURN, MAX_LENGTH, MAX_MATERIAL_SLOTS,
                     MAX_MESH_VERTICES, MAX_RELIEF, MAX_SCALE_FACTOR, MIN_MATERIAL_OFFSET, NORMAL_WEIGHT,
                     NORMAL_WEIGHT_THRESHOLD, PAIR, SCREW_STEPS, SMALLEST_TEXTURE_FEATURE, SUBDIVISION_LEVELS,
                     TEXTURE_CONTRAST, TEXTURE_DEPTH, TEXTURE_INTENSITY, THICKNESS_CLAMP, WINDING)
from .schema import array, boolean, described, integer, number, obj as object_schema, ref, string


class Field:
    def __init__(self, schema, attribute=None, convert=None):
        self.schema = schema
        self.attribute = attribute
        self.convert = convert


def upper(value, target):
    return value.upper()


def radians(value, target):
    return math.radians(value)


def object_of(types, label):
    def convert(name, target):
        other = bpy.data.objects.get(name)
        if other is None or other.name not in bpy.context.scene.objects:
            raise not_found(f"no object named {name} in the scene")
        if other.type not in types:
            raise bad_args(f"{name} is a {other.type.lower()}, not a {label}")
        if other == target:
            raise bad_args(f"{target.name} cannot use itself as the {label}")
        return other

    return convert


def group_of(name, target):
    if name not in target.vertex_groups:
        raise not_found(f"{target.name} has no vertex group named {name}")
    return name


def enum(description, values):
    return string(description, values)


def group_field():
    return Field(string("Vertex group that weights the effect."), "vertex_group", group_of)


def invert_field():
    return Field(boolean("Invert the vertex group weights."), "invert_vertex_group")


def simple(schema, attribute):
    return Field(schema, attribute)


TEXTURE_TYPES = ("clouds", "voronoi", "distorted_noise", "stucci", "marble", "wood", "musgrave")

TEXTURE = object_schema(
    {
        "type": enum("Built-in noise texture.", TEXTURE_TYPES),
        "size": number("Noise scale; smaller values give finer detail.", SMALLEST_TEXTURE_FEATURE, MAX_LENGTH),
        "depth": integer("Detail levels, for clouds and marble.", 0, TEXTURE_DEPTH),
        "intensity": number("Texture brightness, 0 to 2.", 0.0, TEXTURE_INTENSITY),
        "contrast": number("Texture contrast, 0 to 5.", 0.0, TEXTURE_CONTRAST),
    },
    ["type"],
)

SPECS = {
    "displace": {
        "summary": "Displace vertices by a built-in noise texture.",
        "blender": "DISPLACE",
        "required": [],
        "fields": {
            "strength": simple(number("Displacement per texture unit in metres.", -MAX_RELIEF, MAX_RELIEF), "strength"),
            "mid_level": simple(number("Texture value that does not move the surface.", 0.0, FRACTION), "mid_level"),
            "direction": Field(enum("Direction of the displacement.", ["normal", "x", "y", "z", "rgb_to_xyz"]), "direction", upper),
            "space": Field(enum("Space of the x, y and z directions.", ["local", "global"]), "space", upper),
            "texture": Field(TEXTURE),
            "texture_coords": Field(enum("How the texture is mapped.", ["local", "global", "object", "uv"]), "texture_coords", upper),
            "texture_object": Field(ref(string("Object whose space maps the texture, with texture_coords object."), "object"), "texture_coords_object", object_of(("MESH", "EMPTY", "CURVE"), "object")),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "weld": {
        "summary": "Merge vertices that are close together.",
        "blender": "WELD",
        "required": [],
        "fields": {
            "distance": simple(number("Merge vertices closer than this many metres.", 0.0, MAX_LENGTH), "merge_threshold"),
            "mode": Field(enum("all merges any close vertices; connected only those joined by an edge.", ["all", "connected"]), "mode", upper),
            "loose_edges": simple(boolean("connected: also merge the ends of loose edges."), "loose_edges"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "screw": {
        "summary": "Turn a profile around an axis like a lathe or screw.",
        "blender": "SCREW",
        "required": [],
        "fields": {
            "angle": Field(number("Turn in degrees.", -WINDING, WINDING), "angle", radians),
            "steps": simple(integer("Steps per turn in the viewport.", PAIR, SCREW_STEPS), "steps"),
            "render_steps": simple(integer("Steps per turn in renders.", PAIR, SCREW_STEPS), "render_steps"),
            "iterations": simple(integer("Number of turns.", 1, SCREW_STEPS), "iterations"),
            "axis": Field(enum("Axis of the turn.", ["x", "y", "z"]), "axis", upper),
            "offset": simple(number("Shift along the axis per turn in metres.", -MAX_LENGTH, MAX_LENGTH), "screw_offset"),
            "merge": simple(boolean("Merge the seam vertices."), "use_merge_vertices"),
            "merge_distance": simple(number("Seam merge distance in metres.", 0.0, MAX_LENGTH), "merge_threshold"),
            "flip_normals": simple(boolean("Flip the normals."), "use_normal_flip"),
            "recalculate_normals": simple(boolean("Recalculate the normals."), "use_normal_calculate"),
            "smooth_shading": simple(boolean("Shade the result smooth."), "use_smooth_shade"),
        },
    },
    "curve": {
        "summary": "Bend the mesh along a curve.",
        "blender": "CURVE",
        "required": ["curve"],
        "fields": {
            "curve": Field(ref(string("Curve object to bend along."), "object"), "object", object_of(("CURVE",), "curve")),
            "axis": Field(enum("Mesh axis that runs along the curve.", ["pos_x", "pos_y", "pos_z", "neg_x", "neg_y", "neg_z"]), "deform_axis", upper),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "simple_deform": {
        "summary": "Twist, bend, taper or stretch the mesh.",
        "blender": "SIMPLE_DEFORM",
        "required": [],
        "fields": {
            "method": Field(enum("Kind of deformation.", ["twist", "bend", "taper", "stretch"]), "deform_method", upper),
            "angle": Field(number("Twist or bend angle in degrees.", -WINDING, WINDING), "angle", radians),
            "factor": simple(number("Taper or stretch amount.", -MAX_SCALE_FACTOR, MAX_SCALE_FACTOR), "factor"),
            "axis": Field(enum("Axis of the deformation.", ["x", "y", "z"]), "deform_axis", upper),
            "origin": Field(ref(string("Object whose position is the origin of the deformation."), "object"), "origin", object_of(("MESH", "EMPTY", "CURVE"), "object")),
            "limits": simple(array({"type": "number", "minimum": 0.0, "maximum": FRACTION}, "Lower and upper limit of the effect, 0 to 1.", 2, 2), "limits"),
            "lock_x": simple(boolean("Do not deform along x."), "lock_x"),
            "lock_y": simple(boolean("Do not deform along y."), "lock_y"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "wireframe": {
        "summary": "Turn edges into wires.",
        "blender": "WIREFRAME",
        "required": [],
        "fields": {
            "thickness": simple(number("Wire thickness in metres.", 0.0, MAX_LENGTH), "thickness"),
            "offset": simple(number("Shift of the wires, -1 to 1.", -FRACTION, FRACTION), "offset"),
            "replace": simple(boolean("Replace the original surface."), "use_replace"),
            "boundary": simple(boolean("Add wires along open boundaries."), "use_boundary"),
            "even_offset": simple(boolean("Keep the thickness even at corners."), "use_even_offset"),
            "relative_offset": simple(boolean("Scale the offset by the face size."), "use_relative_offset"),
            "crease": simple(boolean("Crease the wire edges."), "use_crease"),
            "crease_weight": simple(number("Crease weight.", 0.0, FRACTION), "crease_weight"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "lattice": {
        "summary": "Deform the mesh with a lattice.",
        "blender": "LATTICE",
        "required": ["lattice"],
        "fields": {
            "lattice": Field(ref(string("Lattice object that deforms the mesh."), "object"), "object", object_of(("LATTICE",), "lattice")),
            "strength": simple(number("Share of the deformation applied.", 0.0, FRACTION), "strength"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "shrinkwrap": {
        "summary": "Wrap the mesh onto another mesh.",
        "blender": "SHRINKWRAP",
        "required": ["target"],
        "fields": {
            "target": Field(ref(string("Mesh object to wrap onto."), "object"), "target", object_of(("MESH",), "mesh")),
            "method": Field(enum("How vertices find the target.", ["nearest_surfacepoint", "project", "nearest_vertex", "target_project"]), "wrap_method", upper),
            "mode": Field(enum("Where vertices end up relative to the surface.", ["on_surface", "inside", "outside", "outside_surface", "above_surface"]), "wrap_mode", upper),
            "offset": simple(number("Distance from the surface in metres.", -MAX_LENGTH, MAX_LENGTH), "offset"),
            "project_limit": simple(number("Largest projection distance in metres; 0 for unlimited.", 0.0, MAX_LENGTH), "project_limit"),
            "subsurf_levels": simple(integer("Subdivision levels of the mesh while wrapping.", 0, SUBDIVISION_LEVELS), "subsurf_levels"),
            "negative_direction": simple(boolean("project: also project against the direction."), "use_negative_direction"),
            "positive_direction": simple(boolean("project: project along the direction."), "use_positive_direction"),
            "cull_faces": Field(enum("project: ignore front or back faces of the target.", ["off", "front", "back"]), "cull_face", upper),
            "project_x": simple(boolean("project: project along x."), "use_project_x"),
            "project_y": simple(boolean("project: project along y."), "use_project_y"),
            "project_z": simple(boolean("project: project along z."), "use_project_z"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "triangulate": {
        "summary": "Split faces into triangles.",
        "blender": "TRIANGULATE",
        "required": [],
        "fields": {
            "quad_method": Field(enum("How quads are split.", ["beauty", "fixed", "fixed_alternate", "shortest_diagonal", "longest_diagonal"]), "quad_method", upper),
            "ngon_method": Field(enum("How larger faces are split.", ["beauty", "clip"]), "ngon_method", upper),
            "min_vertices": simple(integer("Only split faces with at least this many vertices.", FEWEST_SPLIT_CORNERS, MAX_MESH_VERTICES), "min_vertices"),
            "keep_custom_normals": simple(boolean("Keep custom normals."), "keep_custom_normals"),
        },
    },
    "weighted_normal": {
        "summary": "Weight vertex normals by face area or angle.",
        "blender": "WEIGHTED_NORMAL",
        "required": [],
        "fields": {
            "mode": Field(enum("What weights the normals.", ["face_area", "corner_angle", "face_area_with_angle"]), "mode", upper),
            "weight": simple(integer("Strength of the weighting, 1 to 100.", 1, NORMAL_WEIGHT), "weight"),
            "threshold": simple(number("Weights closer than this count as equal.", 0.0, NORMAL_WEIGHT_THRESHOLD), "thresh"),
            "keep_sharp": simple(boolean("Keep sharp edges."), "keep_sharp"),
            "face_influence": simple(boolean("Use face strength."), "use_face_influence"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "bevel": {
        "summary": "Round edges.",
        "blender": "BEVEL",
        "required": [],
        "fields": {
            "width": simple(number("Bevel width in metres.", 0.0, MAX_LENGTH), "width"),
            "segments": simple(integer("Bevel segments.", 1, BEVEL_SEGMENTS), "segments"),
            "limit_method": Field(enum("Which edges to bevel: all, those sharper than angle, those with a bevel weight, or a vertex group.", ["none", "angle", "weight", "vgroup"]), "limit_method", upper),
            "angle": Field(number("limit_method angle: bevel edges sharper than this many degrees.", 0.0, HALF_TURN), "angle_limit", radians),
            "affect": Field(enum("Bevel edges or vertices.", ["edges", "vertices"]), "affect", upper),
            "offset_type": Field(enum("How the width is measured.", ["offset", "width", "depth", "percent", "absolute"]), "offset_type", upper),
            "profile": simple(number("Profile shape; 0.5 is round.", 0.0, FRACTION), "profile"),
            "harden_normals": simple(boolean("Keep flat faces flat-shaded."), "harden_normals"),
            "clamp_overlap": simple(boolean("Keep bevels from overlapping."), "use_clamp_overlap"),
            "loop_slide": simple(boolean("Slide along edge loops."), "loop_slide"),
            "miter_outer": Field(enum("Outer miter pattern.", ["miter_sharp", "miter_patch", "miter_arc"]), "miter_outer", upper),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
    "solidify": {
        "summary": "Give a surface thickness.",
        "blender": "SOLIDIFY",
        "required": [],
        "fields": {
            "thickness": simple(number("Thickness in metres.", -MAX_LENGTH, MAX_LENGTH), "thickness"),
            "offset": simple(number("-1 grows inward, 1 outward, 0 both ways.", -FRACTION, FRACTION), "offset"),
            "even": simple(boolean("Keep the thickness even at corners."), "use_even_offset"),
            "rim": simple(boolean("Fill the rim between the two surfaces."), "use_rim"),
            "rim_only": simple(boolean("Only the rim."), "use_rim_only"),
            "mode": Field(enum("simple extrudes along normals; non_manifold handles complex meshes.", ["extrude", "non_manifold"]), "solidify_mode", upper),
            "thickness_mode": Field(enum("non_manifold: how thickness is kept.", ["fixed", "even", "constraints"]), "nonmanifold_thickness_mode", upper),
            "flip_normals": simple(boolean("Flip the normals."), "use_flip_normals"),
            "thickness_clamp": simple(number("Limit thickness by the neighbouring geometry, 0 to 100.", 0.0, THICKNESS_CLAMP), "thickness_clamp"),
            "material_offset": simple(integer("Material slot shift of the new surface.", MIN_MATERIAL_OFFSET, MAX_MATERIAL_SLOTS), "material_offset"),
            "vertex_group": group_field(),
            "invert_vertex_group": invert_field(),
        },
    },
}


def kind_schemas():
    schemas = {}
    for kind, spec in SPECS.items():
        properties = {name: field.schema for name, field in spec["fields"].items()}
        schemas[kind] = described(object_schema(properties, spec["required"]), f"{spec['summary']} Give this field alone to add that modifier.")
    return schemas


def make_texture(target, settings):
    kind = settings["type"]
    if "depth" in settings and kind not in ("clouds", "marble"):
        raise bad_args("depth works only with the clouds and marble textures")
    texture = bpy.data.textures.new(f"{target.name}_displace", kind.upper())
    for key, attribute in (("size", "noise_scale"), ("depth", "noise_depth"), ("intensity", "intensity"), ("contrast", "contrast")):
        if key in settings:
            setattr(texture, attribute, settings[key])
    return texture


def configure(target, kind, settings, modifier):
    spec = SPECS[kind]
    if "texture_object" in settings and settings.get("texture_coords") != "object":
        raise bad_args("texture_object needs texture_coords object")
    for name, value in settings.items():
        field = spec["fields"][name]
        if name == "texture":
            modifier.texture = make_texture(target, value)
            continue
        converted = field.convert(value, target) if field.convert is not None else value
        setattr(modifier, field.attribute, converted)
