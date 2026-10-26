import copy
import math

from .errors import bad_args
from .limits import MAX_COORDINATE, MAX_NAMES


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


def length(description, default=None, maximum=MAX_COORDINATE):
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


def string(description, enum=None, default=None, max_length=256):
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
    item = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    return array(item, description, 3, 4 if allow_alpha else 3, default)


def names(description, min_items=1, max_items=MAX_NAMES):
    return array({"type": "string", "minLength": 1, "maxLength": 256}, description, min_items, max_items)


def obj(properties, required=()):
    for name in required:
        if name not in properties:
            raise ValueError(f"required field {name} is not a property")
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def validate(schema, value):
    return _check(schema, value, "args")


def _check(schema, value, where):
    kind = schema["type"]
    if kind == "object":
        return _check_object(schema, value, where)
    if kind == "array":
        return _check_array(schema, value, where)
    if kind == "string":
        return _check_string(schema, value, where)
    if kind == "boolean":
        if not isinstance(value, bool):
            raise bad_args(f"{where} must be true or false")
        return value
    if kind in ("number", "integer"):
        return _check_number(schema, value, where)
    raise ValueError(f"unknown schema type {kind}")


def _check_object(schema, value, where):
    if not isinstance(value, dict):
        raise bad_args(f"{where} must be an object")
    properties = schema["properties"]
    unknown = sorted(str(key) for key in value if key not in properties)
    if unknown:
        raise bad_args(f"{where} has unknown field(s): {', '.join(unknown)}")
    cleaned = {}
    for name, field in properties.items():
        if name in value:
            cleaned[name] = _check(field, value[name], f"{where}.{name}")
        elif name in schema["required"]:
            raise bad_args(f"{where}.{name} is required")
        elif "default" in field:
            cleaned[name] = copy.deepcopy(field["default"])
    return cleaned


def _check_array(schema, value, where):
    if not isinstance(value, list):
        raise bad_args(f"{where} must be an array")
    if "minItems" in schema and len(value) < schema["minItems"]:
        raise bad_args(f"{where} needs at least {schema['minItems']} item(s)")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        raise bad_args(f"{where} allows at most {schema['maxItems']} item(s)")
    return [_check(schema["items"], item, f"{where}[{index}]") for index, item in enumerate(value)]


def _check_string(schema, value, where):
    if not isinstance(value, str):
        raise bad_args(f"{where} must be a string")
    if "enum" in schema:
        if value not in schema["enum"]:
            raise bad_args(f"{where} must be one of: {', '.join(schema['enum'])}")
        return value
    if len(value) < schema.get("minLength", 0):
        raise bad_args(f"{where} must not be empty")
    if len(value) > schema.get("maxLength", math.inf):
        raise bad_args(f"{where} is longer than {schema['maxLength']} characters")
    if "\x00" in value:
        raise bad_args(f"{where} contains a NUL character")
    return value


def _check_number(schema, value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise bad_args(f"{where} must be a number")
    if schema["type"] == "integer":
        if isinstance(value, float):
            if not value.is_integer():
                raise bad_args(f"{where} must be a whole number")
            value = int(value)
    elif not math.isfinite(value):
        raise bad_args(f"{where} must be finite")
    else:
        value = float(value)
    if "minimum" in schema and value < schema["minimum"]:
        raise bad_args(f"{where} must be at least {schema['minimum']}")
    if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        raise bad_args(f"{where} must be greater than {schema['exclusiveMinimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        raise bad_args(f"{where} must be at most {schema['maximum']}")
    return value
