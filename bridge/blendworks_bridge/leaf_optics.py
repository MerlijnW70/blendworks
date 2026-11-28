"""Two-sided leaves: cited reflectance and transmittance per leaf type, a canopy's reflectance from them.

Leaves reflect and transmit light diffusely: a green leaf transmits about as much as it reflects in the green, much less
in the red and blue where chlorophyll absorbs. Values are band means of the Rec.709 channels (blue 440-490 nm, green
520-570 nm, red 600-680 nm):
- grass: PROSPECT-5 for a grass blade (Feret et al. 2008; N 1.5, chlorophyll 40 ug/cm2, carotenoids 8 ug/cm2, water
  0.012 cm, dry matter 0.005 g/cm2), within the LOPEX93 grass samples (Hosgood et al. 1994);
- broadleaf: LOPEX93 deciduous leaves (beech, maple, oak), PROSPECT-5 with N 1.8;
- needle: conifer needles transmit far less than flat leaves (Daughtry, Biehl and Ranson 1989; LOPEX93 needles);
- petal: petals carry little pigment and transmit 30 to 60 % of the light they do not reflect (van der Kooi et al. 2016,
  "Functional optics of flowers"); the petal's own colour is its reflectance, the transmittance follows it;
- litter: senescent, fallen leaves (LOPEX93 brown leaves): bright in the red, little transmission in the blue;
- straw: standing dead grass of a dry meadow, paler than fallen leaves (Asner 1998, "Biophysical and biochemical sources
  of variability in canopy reflectance", standing litter of grasslands).
A material keeps its own colour as its reflectance; the transmittance is that colour times the type's T/R ratio per
channel, so textures and per-blade variation carry through. The surface is a Principled reflection mixed with a
Translucent BSDF by f = T / (R + T) (luminance), the Principled colour divided by 1 - f and the translucent colour by f,
so the leaf reflects R and transmits T exactly; T never exceeds 1 - R, so a bright petal cannot scatter more than it
receives. Transmission Weight (a specular, glass-like refraction) is never used.

Canopy reflectance (Goudriaan 1977, "Crop micrometeorology"; Goudriaan and van Laar 1994): with the leaf scattering
coefficient s = R + T, an infinitely deep canopy of horizontal leaves reflects rho_h = (1 - sqrt(1 - s)) / (1 + sqrt(1 - s));
for a direct beam with extinction coefficient k_b over leaves of another inclination rho = 2 k_b / (k_b + k_d) rho_h,
and a finite canopy of leaf area index L over soil of reflectance rho_s reflects
rho + (rho_s - rho) exp(-2 sqrt(1 - s) k_b L).

Grassland albedo: 0.18-0.26 over the broadband solar spectrum (Oke 1987, "Boundary Layer Climates"), most of it near
infrared; 0.03-0.10 in the visible band a render holds (MODIS visible albedo of grassland in the growing season, Gao et al.
2005). Grassland leaf area index 1 to 5, mean 2.5 (Asner, Scurlock and Hicke 2003)."""
import math

import numpy

LUMINANCE = numpy.array([0.2126, 0.7152, 0.0722])
OPTICS = {
    "grass": {"reflectance": (0.06, 0.13, 0.05), "transmittance": (0.04, 0.10, 0.02)},
    "broadleaf": {"reflectance": (0.06, 0.11, 0.045), "transmittance": (0.035, 0.08, 0.015)},
    "needle": {"reflectance": (0.05, 0.09, 0.04), "transmittance": (0.015, 0.035, 0.008)},
    "petal": {"reflectance": (0.6, 0.6, 0.6), "transmittance": (0.3, 0.3, 0.3)},
    "litter": {"reflectance": (0.25, 0.18, 0.08), "transmittance": (0.12, 0.07, 0.02)},
    "straw": {"reflectance": (0.33, 0.27, 0.15), "transmittance": (0.2, 0.15, 0.06)},
}
LEAF_TYPES = tuple(OPTICS)
NEEDLE_SHAPES = ("needle", "tuft", "brush")
GRASS_LAI = (1.0, 5.0)
VISIBLE_GRASS_ALBEDO = (0.03, 0.10)
BROADBAND_GRASS_ALBEDO = (0.18, 0.26)
DIFFUSE_EXTINCTION = 0.8
MEADOW_LAI = 2.5
ERECTOPHILE_MEAN = 63.24
REFERENCE_SUN = 60.0
MEADOW_SOIL = (0.07, 0.05, 0.03)
MIX_NODE = "Leaf Two-Sided"
TRANSLUCENT_NODE = "Leaf Translucent"
CUTOUT_NODE = "Leaf Cutout"


def ratio(leaf_type):
    optics = OPTICS[leaf_type]
    return [t / r for r, t in zip(optics["reflectance"], optics["transmittance"])]


def mix_factor(leaf_type, amount=1.0):
    optics = OPTICS[leaf_type]
    reflected = float(numpy.asarray(optics["reflectance"]) @ LUMINANCE)
    transmitted = float(numpy.asarray(optics["transmittance"]) @ LUMINANCE) * amount
    return transmitted / (reflected + transmitted)


def leaf_type_of_shape(shape):
    return "needle" if shape in NEEDLE_SHAPES else "broadleaf"


def principled_and_output(graph):
    output = next((node for node in graph.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
    output = output or next((node for node in graph.nodes if node.type == "OUTPUT_MATERIAL"), None)
    shader = next((node for node in graph.nodes if node.type == "BSDF_PRINCIPLED"), None)
    return shader, output


def two_sided(graph, leaf_type, amount=1.0, colour=None):
    """Make the material's Principled leaf two-sided: the leaf's colour (colour, else what feeds Base Color) is its
    reflectance, and a Translucent BSDF passes the cited transmittance (times amount; 0 keeps the leaf opaque) to the
    other side. Returns the colour Base Color must take, or None when nothing changed."""
    shader, output = principled_and_output(graph)
    if shader is None or output is None or amount <= 0.0:
        return None
    shader.inputs["Transmission Weight"].default_value = 0.0
    shader.inputs["Subsurface Weight"].default_value = 0.0
    socket = shader.inputs["Base Color"]
    if colour is None:
        colour = socket.links[0].from_socket if socket.is_linked else list(socket.default_value)[:3]
    factor = mix_factor(leaf_type, amount)
    reflected = graph.mix(1.0, colour, [1.0 / (1.0 - factor)] * 3, blend="MULTIPLY", clamp=False)
    transmitted = graph.mix(1.0, colour, [value * amount for value in ratio(leaf_type)], blend="MULTIPLY", clamp=False)
    left = graph.mix(1.0, [1.0, 1.0, 1.0], colour, blend="SUBTRACT", clamp=False)
    bounded = graph.vector_math("MINIMUM", transmitted, left)
    passed = graph.vector_math("SCALE", bounded, scale=1.0 / factor)
    graph.set(socket, reflected)
    translucent = graph.node("ShaderNodeBsdfTranslucent", {"Color": passed}, name=TRANSLUCENT_NODE)
    if shader.inputs["Normal"].is_linked:
        graph.set(translucent.inputs["Normal"], shader.inputs["Normal"].links[0].from_socket)
    through = cut_out(graph, shader, translucent.outputs["BSDF"])
    surface = output.inputs["Surface"]
    source = surface.links[0].from_socket if surface.is_linked else shader.outputs["BSDF"]
    mix = graph.node("ShaderNodeMixShader", {"Fac": factor}, name=MIX_NODE)
    graph.set(mix.inputs[1], source)
    graph.set(mix.inputs[2], through)
    graph.set(surface, mix.outputs["Shader"])
    return reflected


def cut_out(graph, shader, transmitted):
    """The transmitted light keeps to the leaf's outline: the Principled alpha (a cut-out leaf on a card) masks it too."""
    alpha = shader.inputs["Alpha"]
    if not alpha.is_linked and alpha.default_value >= 1.0:
        return transmitted
    clear = graph.node("ShaderNodeBsdfTransparent")
    cut = graph.node("ShaderNodeMixShader", {"Fac": alpha.links[0].from_socket if alpha.is_linked else alpha.default_value}, name=CUTOUT_NODE)
    graph.set(cut.inputs[1], clear.outputs["BSDF"])
    graph.set(cut.inputs[2], transmitted)
    return cut.outputs["Shader"]


def canopy_reflectance(leaf_type, leaf_area_index, soil, sun_elevation, mean_inclination):
    """Reflectance per channel of a canopy of these leaves over soil, for a direct sun, by Goudriaan's two-stream model.
    The beam extinction of leaves at one mean inclination (degrees from horizontal) is that of the ellipsoidal leaf
    angle distribution's limits: G = cos(i) cos(z) for leaves flatter than the sun, else the vertical-leaf value."""
    optics = OPTICS[leaf_type]
    scattering = numpy.asarray(optics["reflectance"]) + numpy.asarray(optics["transmittance"])
    root = numpy.sqrt(1.0 - scattering)
    horizontal = (1.0 - root) / (1.0 + root)
    zenith = math.radians(90.0 - max(sun_elevation, 1.0))
    inclination = math.radians(mean_inclination)
    projection = projected_area(inclination, zenith)
    beam = projection / math.cos(zenith)
    deep = 2.0 * beam / (beam + DIFFUSE_EXTINCTION) * horizontal
    return deep + (numpy.asarray(soil) - deep) * numpy.exp(-2.0 * root * beam * leaf_area_index)


def meadow_colour(leaf_type):
    """Colour of a meadow canopy seen from above: leaf area index 2.5, the mean of grasslands (Asner, Scurlock and Hicke
    2003), erectophile leaves (de Wit 1965, mean inclination 63.2 degrees), over the soil colour of the ground presets,
    under a high sun 60 degrees up."""
    return [round(float(value), 4) for value in canopy_reflectance(leaf_type, MEADOW_LAI, MEADOW_SOIL, REFERENCE_SUN, ERECTOPHILE_MEAN)]


def canopy_colour(cover_class="grass", dryness=0.0):
    """Colour of land covered by this leaf type seen from afar, a dryness share of it dry straw: the one colour near
    blades, the ground layer and distant land share."""
    green = numpy.asarray(meadow_colour(cover_class))
    straw = numpy.asarray(meadow_colour("straw"))
    share = min(max(dryness, 0.0), 1.0)
    return [round(float(value), 4) for value in green * (1.0 - share) + straw * share]


def projected_area(inclination, zenith):
    """Mean projection G of leaves of one inclination, azimuths uniform, on a plane normal to a ray at this zenith angle
    (Ross 1981, eq. for a single inclination class)."""
    if inclination + zenith <= 0.5 * math.pi:
        return math.cos(inclination) * math.cos(zenith)
    beta = math.acos(1.0 / (math.tan(inclination) * math.tan(zenith)))
    return math.cos(inclination) * math.cos(zenith) * (1.0 + 2.0 / math.pi * (math.tan(beta) - beta))
