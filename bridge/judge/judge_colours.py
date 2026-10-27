MAX_ITEMS = 64
NAME_LENGTH = 120
DOMAINS = {"POINT": "point", "CORNER": "corner"}
TYPES = {"BYTE_COLOR": "byte", "FLOAT_COLOR": "float"}


class ColourCollector:
    def __init__(self):
        self.meshes = []

    def add(self, label, mesh):
        attributes = [
            {"name": attribute.name[:NAME_LENGTH], "domain": DOMAINS.get(attribute.domain, attribute.domain.lower()), "type": TYPES.get(attribute.data_type, attribute.data_type.lower())}
            for attribute in mesh.color_attributes
        ]
        self.meshes.append({"mesh": label[:NAME_LENGTH], "attributes": attributes})

    def result(self):
        attributes = [attribute for entry in self.meshes for attribute in entry["attributes"]]
        domains = {domain: sum(1 for attribute in attributes if attribute["domain"] == domain) for domain in DOMAINS.values()}
        types = {kind: sum(1 for attribute in attributes if attribute["type"] == kind) for kind in TYPES.values()}
        without = sorted(entry["mesh"] for entry in self.meshes if not entry["attributes"])
        return {
            "meshes": len(self.meshes),
            "withColours": len(self.meshes) - len(without),
            "attributes": len(attributes),
            "domains": domains,
            "types": types,
            "without": without[:MAX_ITEMS],
            "items": [{"mesh": entry["mesh"], "attributes": entry["attributes"][:MAX_ITEMS]} for entry in sorted(self.meshes, key=lambda entry: entry["mesh"])[:MAX_ITEMS]],
        }
