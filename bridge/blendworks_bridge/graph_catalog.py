class NodeKind:
    def __init__(self, idname, settings=(), owner=None, output_value=False, stops=False):
        self.idname = idname
        self.settings = tuple(settings)
        self.owner = owner
        self.output_value = output_value
        self.stops = stops


KINDS = {
    "principled_bsdf": NodeKind("ShaderNodeBsdfPrincipled", ("distribution", "subsurface_method")),
    "emission": NodeKind("ShaderNodeEmission"),
    "mix_shader": NodeKind("ShaderNodeMixShader"),
    "material_output": NodeKind("ShaderNodeOutputMaterial", ("target",)),
    "noise_texture": NodeKind("ShaderNodeTexNoise", ("noise_dimensions", "noise_type", "normalize")),
    "voronoi_texture": NodeKind("ShaderNodeTexVoronoi", ("voronoi_dimensions", "distance", "feature", "normalize")),
    "wave_texture": NodeKind("ShaderNodeTexWave", ("wave_type", "bands_direction", "rings_direction", "wave_profile")),
    "checker_texture": NodeKind("ShaderNodeTexChecker"),
    "gradient_texture": NodeKind("ShaderNodeTexGradient", ("gradient_type",)),
    "brick_texture": NodeKind("ShaderNodeTexBrick", ("offset_frequency", "squash_frequency", "offset", "squash")),
    "white_noise_texture": NodeKind("ShaderNodeTexWhiteNoise", ("noise_dimensions",)),
    "color_ramp": NodeKind("ShaderNodeValToRGB", ("interpolation", "color_mode", "hue_interpolation"), owner="color_ramp", stops=True),
    "mix": NodeKind("ShaderNodeMix", ("data_type", "factor_mode", "blend_type", "clamp_factor", "clamp_result")),
    "invert_color": NodeKind("ShaderNodeInvert"),
    "hue_saturation": NodeKind("ShaderNodeHueSaturation"),
    "brightness_contrast": NodeKind("ShaderNodeBrightContrast"),
    "gamma": NodeKind("ShaderNodeGamma"),
    "rgb": NodeKind("ShaderNodeRGB", output_value=True),
    "value": NodeKind("ShaderNodeValue", output_value=True),
    "math": NodeKind("ShaderNodeMath", ("operation", "use_clamp")),
    "vector_math": NodeKind("ShaderNodeVectorMath", ("operation",)),
    "map_range": NodeKind("ShaderNodeMapRange", ("data_type", "interpolation_type", "clamp")),
    "clamp": NodeKind("ShaderNodeClamp", ("clamp_type",)),
    "separate_xyz": NodeKind("ShaderNodeSeparateXYZ"),
    "combine_xyz": NodeKind("ShaderNodeCombineXYZ"),
    "separate_color": NodeKind("ShaderNodeSeparateColor", ("mode",)),
    "combine_color": NodeKind("ShaderNodeCombineColor", ("mode",)),
    "rgb_to_bw": NodeKind("ShaderNodeRGBToBW"),
    "mapping": NodeKind("ShaderNodeMapping", ("vector_type",)),
    "texture_coordinate": NodeKind("ShaderNodeTexCoord"),
    "bump": NodeKind("ShaderNodeBump", ("invert",)),
    "normal_map": NodeKind("ShaderNodeNormalMap", ("space", "uv_map", "convention")),
    "displacement": NodeKind("ShaderNodeDisplacement", ("space",)),
    "vector_transform": NodeKind("ShaderNodeVectorTransform", ("vector_type", "convert_from", "convert_to")),
    "geometry": NodeKind("ShaderNodeNewGeometry"),
    "ambient_occlusion": NodeKind("ShaderNodeAmbientOcclusion", ("samples", "inside", "only_local")),
    "attribute": NodeKind("ShaderNodeAttribute", ("attribute_type", "attribute_name")),
    "fresnel": NodeKind("ShaderNodeFresnel"),
    "layer_weight": NodeKind("ShaderNodeLayerWeight"),
}

BY_IDNAME = {kind.idname: name for name, kind in KINDS.items()}
VALUE_SOCKETS = ("VALUE", "INT", "BOOLEAN", "VECTOR", "RGBA")
INPUT_KEYS = {"VALUE": "number", "INT": "number", "BOOLEAN": "boolean", "VECTOR": "vector", "RGBA": "color"}
SETTING_KEYS = ("text", "number", "boolean")
