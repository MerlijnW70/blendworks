"""Reads a material's Principled node and summarises it."""

from .util import rounded, vec

PRINCIPLED_INPUTS = {
    "base_color": "Base Color",
    "metallic": "Metallic",
    "roughness": "Roughness",
    "emission_color": "Emission Color",
    "emission_strength": "Emission Strength",
    "alpha": "Alpha",
}


def principled_node(material):
    if material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def material_summary(material):
    entry = {"name": material.name, "users": material.users - int(material.use_fake_user)}
    node = principled_node(material)
    if node is None:
        entry["base_color"] = vec(material.diffuse_color)
        return entry
    for key, socket_name in PRINCIPLED_INPUTS.items():
        value = node.inputs[socket_name].default_value
        entry[key] = rounded(value) if isinstance(value, float) else vec(value)
    return entry
