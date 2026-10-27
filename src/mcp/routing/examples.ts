type Schema = Record<string, unknown>;

const NAMED_STRINGS: [RegExp, string][] = [
  [/^(path|.+_path)$/, "asset.glb"],
  [/^font$/, "font.ttf"],
  [/material/, "Material"],
  [/^(camera)$/, "Camera"],
  [/^(target|parent|source|cutter|object|name|active|curve|collection|image|low|high)$/, "Cube"],
  [/^(text)$/, "TEXT"],
  [/^(id)$/, "abandoned_parking"],
  [/^(resolution)$/, "2k"],
];

function isRecord(value: unknown): value is Schema {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clampNumber(schema: Schema, integer: boolean): number {
  if (typeof schema["default"] === "number") return schema["default"];
  const minimum = typeof schema["minimum"] === "number" ? schema["minimum"] : undefined;
  const exclusive = typeof schema["exclusiveMinimum"] === "number" ? schema["exclusiveMinimum"] : undefined;
  const maximum = typeof schema["maximum"] === "number" ? schema["maximum"] : undefined;
  let value = 1;
  if (minimum !== undefined && value < minimum) value = minimum;
  if (exclusive !== undefined && value <= exclusive) value = integer ? Math.floor(exclusive) + 1 : exclusive + 1;
  if (maximum !== undefined && value > maximum) value = integer ? Math.floor(maximum) : maximum;
  return integer ? Math.round(value) : value;
}

function stringFor(schema: Schema, key: string): string {
  if (typeof schema["default"] === "string") return schema["default"];
  const named = NAMED_STRINGS.find(([pattern]) => pattern.test(key));
  const value = named?.[1] ?? "Cube";
  const pattern = typeof schema["pattern"] === "string" ? new RegExp(schema["pattern"]) : undefined;
  return pattern === undefined || pattern.test(value) ? value : "a";
}

export function sampleValue(schema: unknown, key: string): unknown {
  if (!isRecord(schema)) return null;
  if ("const" in schema) return schema["const"];
  if (Array.isArray(schema["enum"]) && schema["enum"].length > 0) return schema["default"] ?? schema["enum"][0];
  for (const choice of ["anyOf", "oneOf"]) {
    const options = schema[choice];
    if (Array.isArray(options) && options.length > 0) return sampleValue(options[0], key);
  }
  switch (schema["type"]) {
    case "string":
      return stringFor(schema, key);
    case "number":
      return clampNumber(schema, false);
    case "integer":
      return clampNumber(schema, true);
    case "boolean":
      return typeof schema["default"] === "boolean" ? schema["default"] : true;
    case "array": {
      const count = typeof schema["minItems"] === "number" ? Math.max(1, schema["minItems"]) : 1;
      const item = sampleValue(schema["items"], key.replace(/s$/, ""));
      return Array.from({ length: count }, () => structuredClone(item));
    }
    case "object":
      return sampleObject(schema);
    default:
      return null;
  }
}

export function sampleObject(schema: Schema): Record<string, unknown> {
  const properties = isRecord(schema["properties"]) ? schema["properties"] : {};
  const required = Array.isArray(schema["required"]) ? schema["required"].filter((name): name is string => typeof name === "string") : [];
  const example: Record<string, unknown> = {};
  for (const name of required) example[name] = sampleValue(properties[name], name);
  return example;
}

export function exampleCall(name: string, schema: Schema): string {
  return `${name} ${JSON.stringify(sampleObject(schema))}`;
}
