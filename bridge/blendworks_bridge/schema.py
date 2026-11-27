import copy
import difflib
import json
import math

from .errors import bad_args
from .limits import FRACTION, LIMITS, MAX_COORDINATE, MAX_LENGTH, MAX_NAMES, MAX_PROBLEMS, NAME_LENGTH, limit_of

BOUND_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "minLength",
                  "maxLength")
LIMIT_TAGS = "x-limits"


def number(description, minimum=None, maximum=None, default=None, exclusive_minimum=None):
    schema = {"type": "number", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if exclusive_minimum is not None:
        schema["exclusiveMinimum"] = exclusive_minimum
    if maximum is not None:
        schema["maximum"] = maximum
    if default is not None:
        schema["default"] = default
    return schema


def length(description, default=None, maximum=MAX_LENGTH):
    return number(description, maximum=maximum, default=default, exclusive_minimum=0)


def integer(description, minimum=None, maximum=None, default=None):
    schema = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    if default is not None:
        schema["default"] = default
    return schema


def string(description, enum=None, default=None, max_length=NAME_LENGTH):
    schema = {"type": "string", "description": description}
    if enum is not None:
        schema["enum"] = list(enum)
    else:
        schema["minLength"] = 1
        schema["maxLength"] = max_length
    if default is not None:
        schema["default"] = default
    return schema


def boolean(description, default=None):
    schema = {"type": "boolean", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def array(items, description, min_items=None, max_items=None, default=None):
    schema = {"type": "array", "description": description, "items": items}
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    if default is not None:
        schema["default"] = default
    return schema


def vector3(description, default=None, minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE):
    item = {"type": "number", "minimum": minimum, "maximum": maximum}
    return array(item, description, 3, 3, default)


def color(description, default=None, allow_alpha=True):
    item = {"type": "number", "minimum": 0.0, "maximum": FRACTION}
    return array(item, description, 3, 4 if allow_alpha else 3, default)


def names(description, min_items=1, max_items=MAX_NAMES):
    return array({"type": "string", "minLength": 1, "maxLength": NAME_LENGTH}, description, min_items, max_items)


def domain_bound(schema, keyword):
    """True for bounds that define what kind of value a field holds rather than limit it: the sign of a quantity
    (minimum or exclusiveMinimum 0), at least one of a count (integer minimum 1), a non-empty string, a list that may
    be empty or needs one item, the arity of a short tuple such as a vector or a colour (at most 4 items), a list
    of choices no longer than the choices themselves, and a maximum of 0 (the sign of a quantity)."""
    value = schema.get(keyword)
    if keyword in ("minimum", "exclusiveMinimum") and value == 0:
        return True
    if keyword == "minimum" and value == 1 and schema.get("type") == "integer":
        return True
    if keyword == "minLength" and value == 1:
        return True
    if keyword == "minItems" and value <= 1:
        return True
    if keyword in ("minItems", "maxItems") and schema.get("maxItems", math.inf) <= 4:
        return True
    items = schema.get("items")
    if keyword == "maxItems" and isinstance(items, dict) and "enum" in items and value <= len(items["enum"]):
        return True
    if keyword in ("maximum", "exclusiveMaximum") and value == 0:
        return True
    return False


def bounds(schema, where="args"):
    """(argument, keyword, value, limit name or None) for every bound of a schema that is not a domain bound."""
    found = []
    if not isinstance(schema, dict):
        return found
    tags = schema.get(LIMIT_TAGS, {})
    for keyword in BOUND_KEYWORDS:
        if keyword in schema and not domain_bound(schema, keyword):
            found.append((where, keyword, schema[keyword], tags.get(keyword)))
    for name, field in schema.get("properties", {}).items():
        found.extend(bounds(field, f"{where}.{name}"))
    if isinstance(schema.get("items"), dict):
        found.extend(bounds(schema["items"], f"{where}[]"))
    for key in ("anyOf", "oneOf", "allOf"):
        for part in schema.get(key, []):
            found.extend(bounds(part, where))
    return found


def tag_limits(schema):
    """Record, under x-limits, the named limit each bound of this schema and its parts came from, and keep the
    bounds themselves as plain numbers. Bounds given as plain numbers stay untagged."""
    if isinstance(schema, list):
        for part in schema:
            tag_limits(part)
        return schema
    if not isinstance(schema, dict):
        return schema
    for keyword in BOUND_KEYWORDS:
        value = schema.get(keyword)
        name = limit_of(value)
        if name is not None:
            schema.setdefault(LIMIT_TAGS, {})[keyword] = name
            schema[keyword] = value.plain()
    for key, value in schema.items():
        if key in ("properties", "$defs"):
            for part in value.values():
                tag_limits(part)
        elif key in ("items", "anyOf", "oneOf", "allOf"):
            tag_limits(value)
    return schema


def obj(properties, required=()):
    for name in required:
        if name not in properties:
            raise ValueError(f"required field {name} is not a property")
    for field in properties.values():
        tag_limits(field)
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def validate(schema, value):
    """Check value against schema and return it cleaned, with defaults filled in. Raises one bad_args error that names
    every problem; its problems attribute lists them one by one."""
    cleaned, problems = check(schema, value)
    if problems:
        error = bad_args("; ".join(problem["message"] for problem in problems))
        error.problems = problems
        raise error
    return cleaned


def check(schema, value, where="args", most=MAX_PROBLEMS):
    """Check value against schema without stopping at the first problem: (cleaned value, list of problems). Past
    most problems the rest are only counted, in one closing problem."""
    checker = _Checker(most)
    cleaned = checker.check(schema, value, where)
    return cleaned, checker.listed()


_INVALID = object()


def more_problems(count, where="args", cap=MAX_PROBLEMS):
    return {"argument": where, "message": f"and {count} more problem(s) not listed (limit {cap.key})",
            "limit": {"name": cap.key, "value": cap.plain()}, "instead": "fix the problems listed, then check again"}


class _Checker:
    def __init__(self, most=MAX_PROBLEMS):
        self.problems = []
        self.most = most
        self.dropped = 0

    def listed(self):
        return self.problems + ([more_problems(self.dropped)] if self.dropped else [])

    def fail(self, where, message, value=None, schema=None, keyword=None, shown=None):
        if len(self.problems) >= self.most:
            self.dropped += 1
            return _INVALID
        problem = {"argument": where, "message": f"{where} {message}"}
        if value is not None:
            problem["value"] = shown if shown is not None else _short(value)
        if schema is not None and keyword is not None:
            problem["limit"] = {"keyword": keyword, "value": schema[keyword]}
            name = schema.get(LIMIT_TAGS, {}).get(keyword)
            if name is not None and name in LIMITS:
                entry = LIMITS[name].describe()
                problem["limit"].update({"name": name, "kind": entry["kind"], "reason": entry["reason"]})
                if "instead" in entry:
                    problem["instead"] = entry["instead"]
            problem["message"] += _limit_note(schema, keyword)
            if name is None and domain_bound(schema, keyword):
                problem["limit"].update({"kind": "domain", "reason": "the field's own range, such as the sign of a quantity"})
        self.problems.append(problem)
        return _INVALID

    def check(self, schema, value, where):
        kind = schema["type"]
        if kind == "object":
            return self.check_object(schema, value, where)
        if kind == "array":
            return self.check_array(schema, value, where)
        if kind == "string":
            return self.check_string(schema, value, where)
        if kind == "boolean":
            if not isinstance(value, bool):
                return self.fail(where, f"must be true or false; got {_short(value)}", value)
            return value
        if kind in ("number", "integer"):
            return self.check_number(schema, value, where)
        raise ValueError(f"unknown schema type {kind}")

    def check_object(self, schema, value, where):
        if not isinstance(value, dict):
            return self.fail(where, f"must be an object; got {_short(value)}", value)
        properties = schema["properties"]
        unknown = sorted(str(key) for key in value if key not in properties)
        cleaned = {}
        if schema.get("additionalProperties") is True:
            cleaned.update({key: value[key] for key in value if key not in properties})
        elif unknown:
            for key in unknown:
                close = difflib.get_close_matches(key, list(properties), 3, 0.5)
                hint = f"; did you mean {', '.join(close)}?" if close else f"; known: {', '.join(sorted(properties))}"
                listed = len(self.problems)
                self.fail(f"{where}.{key}", f"is not an argument of this tool{hint}", value[key])
                if close and len(self.problems) > listed:
                    self.problems[-1]["instead"] = ", ".join(close)
        for name, field in properties.items():
            if name in value:
                cleaned[name] = self.check(field, value[name], f"{where}.{name}")
            elif name in schema["required"]:
                self.fail(f"{where}.{name}", "is required")
            elif "default" in field:
                cleaned[name] = copy.deepcopy(field["default"])
        return cleaned

    def check_array(self, schema, value, where):
        if not isinstance(value, list):
            return self.fail(where, f"must be an array; got {_short(value)}", value)
        if "minItems" in schema and len(value) < schema["minItems"]:
            return self.fail(where, f"needs at least {schema['minItems']} item(s); got {len(value)}", value, schema,
                             "minItems", shown=len(value))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return self.fail(where, f"allows at most {schema['maxItems']} item(s); got {len(value)}", value, schema,
                             "maxItems", shown=len(value))
        return [self.check(schema["items"], item, f"{where}[{index}]") for index, item in enumerate(value)]

    def check_string(self, schema, value, where):
        if not isinstance(value, str):
            return self.fail(where, f"must be a string; got {_short(value)}", value)
        if "enum" in schema:
            if value not in schema["enum"]:
                return self.fail(where, f"must be one of: {', '.join(schema['enum'])}; got {_short(value)}", value)
            return value
        if len(value) < schema.get("minLength", 0):
            return self.fail(where, "must not be empty", value)
        if len(value) > schema.get("maxLength", math.inf):
            return self.fail(where, f"is longer than {schema['maxLength']} characters; got {len(value)}", value, schema,
                             "maxLength", shown=len(value))
        name = schema.get(LIMIT_TAGS, {}).get("maxLength")
        if name in LIMITS and LIMITS[name].unit == "bytes" and len(value.encode("utf-8")) > schema["maxLength"]:
            size = len(value.encode("utf-8"))
            return self.fail(where, f"is longer than {schema['maxLength']} bytes in UTF-8; got {size}", value, schema,
                             "maxLength", shown=size)
        if "\x00" in value:
            return self.fail(where, "contains a NUL character", value)
        return value

    def check_number(self, schema, value, where):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return self.fail(where, f"must be a number; got {_short(value)}", value)
        if schema["type"] == "integer":
            if isinstance(value, float):
                if not value.is_integer():
                    return self.fail(where, f"must be a whole number; got {value}", value)
                value = int(value)
        elif not math.isfinite(value):
            return self.fail(where, f"must be finite; got {value}", value)
        else:
            value = float(value)
        if "minimum" in schema and value < schema["minimum"]:
            return self.fail(where, f"must be at least {schema['minimum']}; got {value}", value, schema, "minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            return self.fail(where, f"must be greater than {schema['exclusiveMinimum']}; got {value}", value, schema,
                             "exclusiveMinimum")
        if "maximum" in schema and value > schema["maximum"]:
            return self.fail(where, f"must be at most {schema['maximum']}; got {value}", value, schema, "maximum")
        return value


def _short(value):
    text = json.dumps(value, default=str)
    return value if len(text) <= 80 else text[:77] + "..."


def _limit_note(schema, keyword):
    name = schema.get(LIMIT_TAGS, {}).get(keyword)
    if name is None or name not in LIMITS:
        return ""
    entry = LIMITS[name].describe()
    note = f" (limit {name}: {entry['reason']}"
    if "instead" in entry:
        note += f" Use instead: {entry['instead']}."
    return note + ")"


def point2(description=None):
    item = {"type": "number", "minimum": -MAX_COORDINATE, "maximum": MAX_COORDINATE}
    return array(item, description or "Point [x, y] in metres.", 2, 2)


def point3(description=None):
    item = {"type": "number", "minimum": -MAX_COORDINATE, "maximum": MAX_COORDINATE}
    return array(item, description or "Point [x, y, z] in metres.", 3, 3)


def points2(description, min_items, max_items, default=None):
    return array(point2(), description, min_items, max_items, default)


def points3(description, min_items, max_items, default=None):
    return array(point3(), description, min_items, max_items, default)


def indices(description, min_items=1, max_items=200_000):
    return array({"type": "integer", "minimum": 0}, description, min_items, max_items)


REF = "x-ref"
REF_KINDS = ("object", "material", "image", "collection")
EXISTS = "exists"
CREATES = "creates"
REPLACES = "replaces"
ENSURES = "ensures"
REF_USES = (EXISTS, CREATES, REPLACES, ENSURES)


def ref(schema, kind, use=EXISTS):
    """Mark a string field, or the items of a names field, as the name of a scene datablock, for validate:
    exists: must exist before the call; creates: must be unused and is made by the call; replaces: made, or rebuilt
    when it exists; ensures: made when missing."""
    if kind not in REF_KINDS or use not in REF_USES:
        raise ValueError(f"unknown reference {kind} {use}")
    target = schema["items"] if schema.get("type") == "array" else schema
    if target.get("type") != "string":
        raise ValueError("a reference is a string or an array of strings")
    target[REF] = {"kind": kind, "use": use}
    return schema


def described(schema, description):
    return {**schema, "description": description}
