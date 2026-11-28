"""Canopy cover on the ground.

The canopy over the ground: each woody plant's crown shades a disc of its crown radius with its opacity, softening
over the outer fifth, and crowns combine as independent layers (cover = 1 - product of (1 - opacity)), the Beer-Lambert
view of gaps in a canopy (Monsi and Saeki 1953). The cover is written on the ground meshes as a float point attribute
that ground cover, the ground material and the meadow fields read: litter and moss gather where it is high, grass thins."""
import numpy
from mathutils.kdtree import KDTree

from .commands.procedural import material_layer
from .land_field import smoothstep
from .registry import COMMANDS
from .schema import validate

OPACITY = {"mature": 0.85, "young": 0.7, "sapling": 0.4, "shrub": 0.8}
SPECIES_OPACITY = {"birch": 0.65, "pine": 0.75, "willow": 0.8, "olive": 0.7}
SOFT_EDGE = (0.8, 1.15)
LITTER = {"color": [0.12, 0.075, 0.04], "pebble_color": [0.2, 0.15, 0.1], "moisture": 0.45, "pebbles": 0.1, "clod_size": 0.03}
LITTER_RANGE = (0.12, 0.65)
MOSS_RANGE = (0.5, 0.95)
MOSS_PATCHES = 0.35
MOSS_SHARE = 0.55


def opacity_of(klass_name, species):
    if klass_name == "shrub":
        return OPACITY["shrub"]
    return OPACITY[klass_name] * SPECIES_OPACITY.get(species, OPACITY["mature"]) / OPACITY["mature"]


def ground_points(obj):
    mesh = obj.data
    local = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float64)
    mesh.vertices.foreach_get("co", local)
    matrix = numpy.array(obj.matrix_world)
    return local.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]


def cover_at(points, crowns):
    """Canopy cover 0 to 1 at plan points from crowns given as (x, y, radius, opacity) rows."""
    gaps = numpy.zeros(len(points))
    if len(points) == 0 or len(crowns) == 0:
        return 1.0 - numpy.exp(gaps)
    tree = KDTree(len(points))
    for index, (x, y) in enumerate(points[:, :2].tolist()):
        tree.insert((x, y, 0.0), index)
    tree.balance()
    for x, y, radius, opacity in crowns.tolist():
        found = tree.find_range((x, y, 0.0), radius * SOFT_EDGE[1])
        if not found:
            continue
        indices = numpy.fromiter((entry[1] for entry in found), dtype=numpy.int64, count=len(found))
        distance = numpy.fromiter((entry[2] for entry in found), dtype=numpy.float64, count=len(found))
        shade = opacity * (1.0 - smoothstep(SOFT_EDGE[0] * radius, SOFT_EDGE[1] * radius, distance))
        gaps[indices] += numpy.log1p(-numpy.minimum(shade, 0.999))
    return 1.0 - numpy.exp(gaps)


def write_canopy(objects, crowns, attribute):
    """Write the cover on every ground object; returns per object the vertices, mean and largest cover."""
    report = {}
    for obj in objects:
        values = cover_at(ground_points(obj), crowns).astype(numpy.float32)
        mesh = obj.data
        existing = mesh.attributes.get(attribute)
        if existing is not None and (existing.domain != "POINT" or existing.data_type != "FLOAT"):
            mesh.attributes.remove(existing)
            existing = None
        target = existing or mesh.attributes.new(attribute, "FLOAT", "POINT")
        target.data.foreach_set("value", values)
        mesh.update()
        report[obj.name] = {"vertices": len(values), "mean": round(float(values.mean()), 5) if len(values) else 0.0,
                            "max": round(float(values.max()), 5) if len(values) else 0.0, "covered_share": round(float((values > 0.5).mean()), 5) if len(values) else 0.0}
    return report


def shade_ground(ctx, objects, attribute, seed):
    """Leaf litter over the soil where the canopy closes and moss in patches in deep shade, layered onto each ground
    material through the canopy attribute."""
    materials = []
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material is not None and slot.material not in materials:
                materials.append(slot.material)
    layered = []
    for material in materials:
        if not material.use_nodes or not any(node.type == "BSDF_PRINCIPLED" for node in material.node_tree.nodes):
            continue
        litter = {"material": material.name, "mask": "attribute", "attribute": attribute, "value_min": LITTER_RANGE[0], "value_max": LITTER_RANGE[1], "soil": LITTER}
        material_layer(ctx, validate(COMMANDS["material_layer"].schema, litter))
        moss = {"material": material.name, "mask": "attribute", "attribute": attribute, "value_min": MOSS_RANGE[0], "value_max": MOSS_RANGE[1],
                "with_masks": ["noise"], "amount": MOSS_SHARE, "mask_scale": MOSS_PATCHES, "seed": seed, "moss": {}}
        material_layer(ctx, validate(COMMANDS["material_layer"].schema, moss))
        layered.append(material.name)
    return layered


def crown_rows(plants, klass_names):
    woody = plants["layer"] <= 1
    rows = []
    for index in numpy.flatnonzero(woody).tolist():
        klass = klass_names[int(plants["klass"][index])]
        rows.append((plants["xy"][index][0], plants["xy"][index][1], plants["radius"][index], opacity_of(klass, plants["species"][index])))
    return numpy.array(rows, dtype=numpy.float64).reshape(-1, 4)

