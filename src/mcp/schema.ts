export type JsonSchema = Record<string, unknown>;

export interface Nearest {
  name: string;
  when: string;
}

export interface BridgeCommand {
  name: string;
  description: string;
  family: string | undefined;
  intents: string[];
  nearest: Nearest[];
  inputSchema: JsonSchema & { type: "object" };
  pathFields: string[];
  dangerous: boolean;
  mutates: boolean;
  destructive: boolean;
  writesFiles: boolean;
  internal: boolean;
  timeoutMs: number;
  maxTimeoutMs: number;
}

export const FALLBACK_TIMEOUT_MS = 120_000;
export const FALLBACK_MAX_TIMEOUT_MS = 600_000;

const KEPT_KEYWORDS = new Set([
  "type",
  "description",
  "enum",
  "const",
  "default",
  "minimum",
  "maximum",
  "exclusiveMinimum",
  "exclusiveMaximum",
  "multipleOf",
  "minLength",
  "maxLength",
  "pattern",
  "format",
  "minItems",
  "maxItems",
  "uniqueItems",
]);

const PATH_FIELD = /^(path|.+_path)$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

export function convertSchema(schema: unknown): JsonSchema {
  if (!isRecord(schema)) return {};
  const out: JsonSchema = {};
  for (const [key, value] of Object.entries(schema)) {
    if (KEPT_KEYWORDS.has(key)) out[key] = structuredClone(value);
  }
  if (schema["items"] !== undefined) {
    out["items"] = Array.isArray(schema["items"]) ? schema["items"].map(convertSchema) : convertSchema(schema["items"]);
  }
  for (const key of ["anyOf", "oneOf", "allOf"]) {
    const options = schema[key];
    if (Array.isArray(options)) out[key] = options.map(convertSchema);
  }
  if (schema["type"] === "object" || isRecord(schema["properties"])) Object.assign(out, convertObject(schema));
  return out;
}

function convertObject(schema: Record<string, unknown>): JsonSchema & { type: "object" } {
  const properties: Record<string, JsonSchema> = {};
  const fields = isRecord(schema["properties"]) ? schema["properties"] : {};
  for (const [name, field] of Object.entries(fields)) properties[name] = convertSchema(field);
  const out: JsonSchema & { type: "object" } = { type: "object", properties, additionalProperties: false };
  const description = text(schema["description"]);
  if (description !== undefined) out["description"] = description;
  const required = Array.isArray(schema["required"]) ? schema["required"].filter((name): name is string => typeof name === "string" && name in properties) : [];
  if (required.length > 0) out["required"] = required;
  return out;
}

function pathFieldsOf(schema: JsonSchema): string[] {
  const properties = isRecord(schema["properties"]) ? schema["properties"] : {};
  return Object.entries(properties)
    .filter(([name, field]) => PATH_FIELD.test(name) || (isRecord(field) && field["format"] === "path"))
    .map(([name]) => name);
}

function phrases(value: unknown): string[] {
  return Array.isArray(value) ? value.flatMap((entry) => (text(entry) === undefined ? [] : [text(entry)!])) : [];
}

function nearestOf(value: unknown): Nearest[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).flatMap((entry) => {
    const name = text(entry["name"]);
    const when = text(entry["when"]);
    return name === undefined || when === undefined || !/^[a-z][a-z0-9_]*$/.test(name) ? [] : [{ name, when }];
  });
}

function seconds(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.round(value * 1000) : undefined;
}

export function commandsFromDescribe(describe: Record<string, unknown>): BridgeCommand[] {
  const commands = Array.isArray(describe["commands"]) ? describe["commands"] : [];
  return commands.filter(isRecord).flatMap((command) => {
    const name = text(command["name"]);
    if (name === undefined || !/^[a-z][a-z0-9_]*$/.test(name)) return [];
    const inputSchema = convertObject(isRecord(command["schema"]) ? command["schema"] : {});
    const timeoutMs = seconds(command["timeout"]) ?? FALLBACK_TIMEOUT_MS;
    const dangerous = command["dangerous"] === true;
    return [
      {
        name,
        description: text(command["description"]) ?? `Runs the Blender bridge command ${name}.`,
        family: text(command["family"]),
        intents: phrases(command["intents"]),
        nearest: nearestOf(command["nearest"]),
        inputSchema,
        pathFields: pathFieldsOf(inputSchema),
        dangerous,
        mutates: command["mutates"] !== false,
        destructive: command["destructive"] === true || dangerous,
        writesFiles: command["writes_files"] === true,
        internal: command["internal"] === true,
        timeoutMs,
        maxTimeoutMs: Math.max(seconds(command["max_timeout"]) ?? FALLBACK_MAX_TIMEOUT_MS, timeoutMs),
      },
    ];
  });
}
