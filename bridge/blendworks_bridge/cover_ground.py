"""Meadow ground layer in the materials.

The ground under a meadow: its material reads the meadow fields, so the soil and the green under and between the cover
carry the meadow's colour structure at every distance. Three scales, none repeating (gradient noise, no images):

- macro, tens to hundreds of metres: the fields themselves (moisture, soil depth, grazing, shade), and where a mesh has no
  fields a broad noise of 150 m stands in for moisture;
- meso, 1 to 10 m: the grazing mosaic, trodden patches and paths of the fields, and noise of 6 m and 2 m in the dry share;
- micro, centimetres: noise of 5 cm and the material's own texture, a quarter of the result.

The colours are green grass from deep (moist) to fresh, straw where it is dry, moss in damp shade, bare and wet soil on
paths and trodden ground, and the petal colour of the flower drifts by the share of the ground their flowers cover."""
from .errors import BAD_ARGS, BridgeError, bad_args
from .meadow_fields import FIELDS, PREFIX, PRESENCE
from .nodes import Graph, find_socket

BLOOM_ATTRIBUTE = "meadow_bloom"
BLOOM_SHARE = "meadow_bloom_share"
MIX_NAME = "meadow_ground_mix"
LUSH = (0.05, 0.11, 0.025)
STRAW = (0.2, 0.165, 0.075)
MOSS = (0.035, 0.07, 0.015)
SOIL = (0.09, 0.065, 0.04)
TRODDEN = (0.09, 0.09, 0.045)
FALLBACK = {"moisture": 0.4, "soil": 0.5, "disturbance": 0.0, "shade": 0.0, "grazing": 0.5}
MACRO = 150.0
MESO = (6.0, 2.0)
MICRO = 0.05
OWN_TEXTURE = 0.25
DRY_BY_MOISTURE = 1.4
DRY_BY_SOIL = 0.5
DRY_BY_GRAZING = 0.3
DARKER_WHEN_MOIST = 0.4


def principled(material):
    tree = material.node_tree
    if tree is None:
        raise bad_args(f"{material.name} has no node tree")
    output = next((node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
    if output is not None and output.inputs["Surface"].is_linked and output.inputs["Surface"].links[0].from_node.type == "BSDF_PRINCIPLED":
        return output.inputs["Surface"].links[0].from_node
    found = [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"]
    if not found:
        raise bad_args(f"{material.name} has no Principled BSDF")
    return found[0]


def field(graph, name, presence, stand_in):
    reader = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=PREFIX + name).outputs["Fac"]
    return graph.mix(presence, stand_in, reader, data_type="FLOAT")


def smooth(graph, value, low, high):
    return graph.map_range(value, low, high, 0.0, 1.0, "SMOOTHSTEP")


def scaled(graph, colour, factor):
    return graph.mix(1.0, colour, graph.node("ShaderNodeCombineXYZ", {"X": factor, "Y": factor, "Z": factor}).outputs[0], blend="MULTIPLY")


def meadow_colour(graph, position, values):
    moisture, soil, disturbance, shade, grazing = (values[name] for name in FIELDS)
    meso_broad = graph.noise(position, 1.0 / MESO[0], detail=2.0).outputs["Fac"]
    meso_fine = graph.noise(position, 1.0 / MESO[1], detail=2.0).outputs["Fac"]
    dry = graph.math("MULTIPLY_ADD", graph.math("SUBTRACT", 0.55, moisture), DRY_BY_MOISTURE, 0.15)
    dry = graph.math("MULTIPLY_ADD", graph.math("SUBTRACT", 0.5, soil), DRY_BY_SOIL, dry)
    dry = graph.math("MULTIPLY_ADD", graph.math("SUBTRACT", 0.5, grazing), DRY_BY_GRAZING, dry)
    dry = graph.math("MULTIPLY_ADD", graph.math("SUBTRACT", meso_broad, 0.5), 0.5, dry)
    dry = graph.math("MULTIPLY_ADD", graph.math("SUBTRACT", meso_fine, 0.5), 0.25, dry, clamp=True)
    grass = scaled(graph, graph.mix(dry, list(LUSH), list(STRAW)), graph.math("MULTIPLY_ADD", moisture, -DARKER_WHEN_MOIST, 1.1))
    moss = graph.math("MULTIPLY", smooth(graph, moisture, 0.45, 0.8), smooth(graph, shade, 0.25, 0.7))
    ground = graph.mix(moss, grass, list(MOSS))
    ground = graph.mix(smooth(graph, disturbance, 0.25, 0.6), ground, list(TRODDEN))
    soil_colour = scaled(graph, list(SOIL), graph.math("MULTIPLY_ADD", moisture, -0.4, 1.0))
    return graph.mix(smooth(graph, disturbance, 0.7, 0.95), ground, soil_colour)


def meadow_ground(material):
    """Insert the meadow ground into material's base colour; False when it is already there."""
    shader = principled(material)
    tree = material.node_tree
    if tree.nodes.get(MIX_NAME) is not None:
        return False
    graph = Graph(tree)
    socket = shader.inputs["Base Color"]
    own = graph.source_of(socket)
    position = graph.node("ShaderNodeNewGeometry").outputs["Position"]
    presence = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=PRESENCE).outputs["Fac"]
    broad = graph.noise(position, 1.0 / MACRO, detail=3.0).outputs["Fac"]
    stand_ins = dict(FALLBACK)
    stand_ins["moisture"] = graph.math("MULTIPLY_ADD", graph.math("SUBTRACT", broad, 0.5), 0.6, FALLBACK["moisture"])
    values = {name: field(graph, name, presence, stand_ins[name]) for name in FIELDS}
    colour = meadow_colour(graph, position, values)
    bloom = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=BLOOM_ATTRIBUTE).outputs["Color"]
    share = graph.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=BLOOM_SHARE).outputs["Fac"]
    colour = graph.mix(share, colour, bloom)
    micro = graph.noise(position, 1.0 / MICRO, detail=3.0).outputs["Fac"]
    colour = scaled(graph, colour, graph.math("MULTIPLY_ADD", micro, 0.5, 0.75))
    mix = graph.node("ShaderNodeMix", data_type="RGBA", blend_type="MIX", clamp_factor=True)
    mix.name = MIX_NAME
    find_socket(mix.inputs, "Factor_Float").default_value = OWN_TEXTURE
    graph.set(find_socket(mix.inputs, "A_Color"), colour)
    graph.set(find_socket(mix.inputs, "B_Color"), own)
    graph.links.new(find_socket(mix.outputs, "Result_Color"), socket)
    return True


def shade_materials(objects):
    """Give every material of the objects the meadow ground; materials without a Principled BSDF are skipped."""
    changed, skipped, seen = [], [], set()
    for obj in objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.name in seen:
                continue
            seen.add(material.name)
            try:
                meadow_ground(material)
            except BridgeError as error:
                if error.code != BAD_ARGS:
                    raise
                skipped.append(material.name)
                continue
            changed.append(material.name)
    return changed, skipped
