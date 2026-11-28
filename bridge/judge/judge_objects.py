"""The object table of the scene being judged."""

from math import inf

from judge_common import distance, rounded

MAX_OBJECTS = 1024
NAME_LENGTH = 120


class ObjectTable:
    def __init__(self):
        self.entries = {}
        self.order = []

    def add(self, name, triangles, low, high, origin, materials):
        entry = self.entries.get(name)
        if entry is None:
            entry = {"triangles": 0, "low": [inf, inf, inf], "high": [-inf, -inf, -inf], "origin": list(origin), "materials": set(), "instances": 0}
            self.entries[name] = entry
            self.order.append(name)
        entry["triangles"] += triangles
        entry["instances"] += 1
        entry["materials"].update(materials)
        for axis in range(3):
            entry["low"][axis] = min(entry["low"][axis], low[axis])
            entry["high"][axis] = max(entry["high"][axis], high[axis])

    def result(self):
        listed = []
        for name in sorted(self.order)[:MAX_OBJECTS]:
            entry = self.entries[name]
            low, high, origin = entry["low"], entry["high"], entry["origin"]
            if low[0] == inf:
                low = high = list(origin)
            centre = [(low[axis] + high[axis]) / 2 for axis in range(3)]
            bottom_centre = [centre[0], centre[1], low[2]]
            listed.append(
                {
                    "name": name[:NAME_LENGTH],
                    "instances": entry["instances"],
                    "triangles": entry["triangles"],
                    "bounds": {"min": rounded(low), "max": rounded(high)},
                    "size": rounded([high[axis] - low[axis] for axis in range(3)]),
                    "origin": {
                        "point": rounded(origin),
                        "bottomCentreDistance": round(distance(origin, bottom_centre), 6),
                        "centreDistance": round(distance(origin, centre), 6),
                    },
                    "materials": sorted(material[:NAME_LENGTH] for material in entry["materials"])[:64],
                }
            )
        return {"count": len(self.order), "items": listed}
