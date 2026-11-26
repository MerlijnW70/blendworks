from .. import liquid_light, liquid_presets, liquid_shader
from ..errors import bad_args
from ..registry import command
from ..schema import array, color, length, names, number, string
from ..util import get_object

RGB = {"type": "number", "minimum": 0.0, "maximum": 1_000_000.0}
OVERRIDES = ("ior", "absorption", "scattering", "concentration", "roughness", "temperature", "crust", "color")


def resolved(args):
    entry = liquid_presets.preset(args["preset"])
    entry["preset"] = args["preset"]
    if "temperature" in args or "crust" in args:
        if entry["mode"] != "emissive":
            raise bad_args("temperature and crust are for lava and molten_metal")
    if "color" in args and entry["mode"] != "opaque":
        raise bad_args("color is for opaque liquids (milk, paint, mud); clear liquids take absorption")
    for key in ("ior", "absorption", "scattering", "concentration", "roughness", "crust"):
        if key in args:
            entry[key] = args[key]
    if "temperature" in args:
        entry["temperature"] = args["temperature"] + liquid_light.CELSIUS
    if "color" in args:
        if "base_color" not in entry:
            raise bad_args(f"{args['preset']} takes its colour from its scattering; give scattering and absorption instead")
        entry["base_color"] = list(args["color"][:3])
    return entry


def describe_entry(entry):
    report = {"mode": entry["mode"], "ior": entry["ior"], "roughness": entry["roughness"], "viscosity": entry["viscosity"],
              "density": entry["density"], "surface_tension": entry["surface_tension"],
              "capillary_length": round(liquid_presets.capillary_length(entry), 6), "sources": entry["sources"]}
    if entry["mode"] == "clear":
        absorption, scattering = liquid_shader.coefficients(entry)
        report["absorption"] = [round(value, 6) for value in absorption]
        report["scattering"] = [round(value, 6) for value in scattering]
        report["absorption_distance"] = [round(1.0 / value, 6) if value > 0 else None for value in absorption]
        report["transmittance_1cm"] = [round(value, 6) for value in liquid_light.transmittance(absorption, scattering, 0.01)]
    elif entry["mode"] == "opaque":
        colour, free_path = liquid_shader.opaque_parameters(entry)
        report["diffuse_color"] = [round(value, 6) for value in colour]
        report["mean_free_path"] = [round(value, 9) for value in free_path]
    else:
        report["temperature_celsius"] = round(entry["temperature"] - liquid_light.CELSIUS, 3)
        report["emissivity"] = entry["emissivity"]
        report["luminance"] = round(entry["emissivity"] * liquid_light.blackbody_luminance(entry["temperature"]), 3)
        report["emission_strength"] = round(liquid_light.emission_strength(entry["temperature"], entry["emissivity"]), 6)
        report["crust"] = entry["crust"]
    if entry.get("foam"):
        report["foam"] = entry["foam"]
    return report


@command(
    "material_liquid",
    "Physically based liquid material: water (fresh, sea, muddy), wine, beer, oil, milk, juice, coffee, paint, honey, syrup, mud, lava and molten metal.",
    {
        "preset": string("Liquid preset.", list(liquid_presets.PRESETS)),
        "name": string("Material name; created, or rebuilt when it exists. Default: the preset name."),
        "objects": names("Objects to give the material.", 1, 256),
        "ior": number("Index of refraction.", 1.0, 4.0),
        "absorption": array(RGB, "Absorption coefficient per metre, red, green, blue.", 3, 3),
        "scattering": array(RGB, "Scattering coefficient per metre, red, green, blue.", 3, 3),
        "concentration": number("Multiply absorption and scattering, as diluting (below 1) or concentrating the liquid.", 0.0, 100.0),
        "roughness": number("Surface roughness.", 0.0, 1.0),
        "color": color("Opaque liquids (paint, mud): the diffuse colour.", allow_alpha=False),
        "temperature": number("Lava and molten metal: core temperature in degrees Celsius.", 400.0, 3000.0),
        "crust": number("Lava and molten metal: share of the surface under cool crust, 0 to 1.", 0.0, 1.0),
        "crust_scale": length("Lava and molten metal: size of the crust plates in metres.", 0.4, 1000.0),
    },
    ["preset"],
    family="liquids",
    intents=("water material with refraction and depth colour", "red wine or milk material", "glowing lava with a dark crust", "honey or oil material"),
    nearest=(("liquid_fill", "to fill a container with liquid"), ("liquid_body", "for lakes, rivers, the ocean and puddles")),
)
def material_liquid(ctx, args):
    entry = resolved(args)
    targets = [get_object(name) for name in args.get("objects", [])]
    for target in targets:
        if target.type not in ("MESH", "CURVE"):
            raise bad_args(f"{target.name} cannot take a material")
    name = args.get("name", args["preset"])
    material = liquid_shader.build(name, entry, crust_scale=args.get("crust_scale", 0.4))
    for target in targets:
        target.data.materials.clear()
        target.data.materials.append(material)
    report = {"name": material.name, "preset": args["preset"], "objects": [target.name for target in targets],
              "overrides": sorted(key for key in OVERRIDES if key in args)}
    report.update(describe_entry(entry))
    if entry["mode"] == "clear" and max(liquid_shader.coefficients(entry)[1]) > 0:
        report["note"] = "scattering renders as a volume; clear liquids need closed meshes or a surface over opaque ground"
    report["preview_color"] = [round(value, 4) for value in liquid_shader.preview_colour(entry)]
    return report
