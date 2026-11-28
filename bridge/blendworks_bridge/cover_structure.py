"""Ground cover side of the meadow fields.

ground_cover's side of the meadow fields: when its populations respond to them it reads the fields from the target
(or computes them), lays out the flower drifts, and afterwards writes the drifts' bloom on the target and gives its
materials the meadow ground."""
import numpy

from .cover_ground import BLOOM_ATTRIBUTE, BLOOM_SHARE, shade_materials
from .liquid_world import vertex_points, write_point_attribute
from .meadow_drifts import Drifts, drift_species
from .meadow_fields import Settings, fields_for
from .meadow_inputs import scene_objects
from .meadow_rules import FieldSampler, uses_fields
from .limits import LEAST_PATH_POINTS, MOST_PATH_POINTS
from .schema import EXISTS, names, points3, ref, string

MODES = ("auto", "on", "off")
PATH_MODES = ("auto", "none")

PROPERTIES = {
    "structure": string("Meadow fields: auto computes them (or reads them from the target) when a population responds to them, on always, off never. With them the target's materials carry the meadow's colour structure.", list(MODES), "auto"),
    "shade": ref(names("Objects whose shadow along the sun shades the ground in the fields: crowns, shrubs, rocks. Default: trees and obstacles."), "object", EXISTS),
    "paths": string("auto: worn paths between the meadow's gates and its water; none: no paths.", list(PATH_MODES), "auto"),
    "path_points": points3("Join these points [x, y, z] in metres with the paths instead of the gates and the water.", LEAST_PATH_POINTS, MOST_PATH_POINTS),
}


def wanted(args, populations):
    if args.get("structure", "auto") == "off":
        return False
    return args.get("structure") == "on" or any(uses_fields(population) for population in populations)


def settings_of(args):
    shade = args.get("shade")
    if shade is None:
        shade = list(dict.fromkeys(list(args.get("trees") or []) + list(args.get("obstacles") or [])))
    return Settings(args["seed"], scene_objects(shade), scene_objects(args.get("obstacles") or []), args.get("paths", "auto"), args.get("path_points"))


class Structure:
    def __init__(self, args, target, surface, populations, depsgraph, scene):
        values, lines, report = fields_for(target, scene, depsgraph, settings_of(args))
        self.sampler = FieldSampler(surface, values, lines)
        self.values = values
        moisture = numpy.asarray(values["moisture"], dtype=float)[surface.vertex_ids]
        self.drifts = Drifts(surface, moisture, drift_species(populations), args["seed"])
        self.report = report

    def finish(self, target, depsgraph):
        """Write the bloom of the drifts on the target and give its materials the meadow ground."""
        points = vertex_points(target)
        evaluated = len(target.evaluated_get(depsgraph).data.vertices)
        if len(points) and evaluated == len(points):
            colour, amount = self.drifts.bloom(points)
            write_bloom(target.data, colour, amount)
            self.report["bloom"] = {"mean": round(float(amount.mean()), 4), "max": round(float(amount.max()), 4)}
        changed, skipped = shade_materials([target])
        self.report["materials"] = changed
        if skipped:
            self.report["materials_skipped"] = skipped
        self.report["drifts"] = {name: len(centres) for name, centres in self.drifts.centres.items()}
        return self.report


def write_bloom(mesh, colour, amount):
    existing = mesh.attributes.get(BLOOM_ATTRIBUTE)
    if existing is not None:
        mesh.attributes.remove(existing)
    attribute = mesh.attributes.new(BLOOM_ATTRIBUTE, "FLOAT_COLOR", "POINT")
    rgba = numpy.column_stack([colour, numpy.ones(len(amount))]).astype(numpy.float32)
    attribute.data.foreach_set("color", rgba.ravel())
    write_point_attribute(mesh, BLOOM_SHARE, amount)
    mesh.update()
