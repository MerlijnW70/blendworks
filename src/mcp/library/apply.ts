import type { CallOutcome } from "../connection.js";
import type { BridgeArgs } from "../protocol.js";
import type { BridgeCommand, JsonSchema } from "../schema.js";
import { confineArgs } from "../tools.js";
import type { Workspace } from "../workspace.js";
import { ASSET_TYPES, type AssetType, LibraryError } from "./common.js";
import { assetFolderPath, type LicenseRecord, readLocal, verifyLocal } from "./store.js";

export interface BridgeAccess {
  commands: BridgeCommand[];
  request(cmd: string, args: BridgeArgs, options?: { signal?: AbortSignal }): Promise<CallOutcome>;
}

export interface ApplyRequest {
  id: string;
  type?: AssetType | undefined;
  object?: string | undefined;
  material?: string | undefined;
  strength?: number | undefined;
  rotation?: number | undefined;
}

export interface Applied {
  record: LicenseRecord;
  steps: { command: string; result: Record<string, unknown> }[];
  notices: string[];
  notWired?: string[];
}

type Role = "base_color" | "normal" | "roughness" | "metallic" | "ao" | "height" | "alpha" | "orm";

const ROLE_OF_MAP: Record<string, Role> = {
  Diffuse: "base_color",
  nor_gl: "normal",
  nor_dx: "normal",
  Rough: "roughness",
  Metal: "metallic",
  AO: "ao",
  Displacement: "height",
  Mask: "alpha",
  arm: "orm",
};

const ROLE_NAMES: Record<Role, string[]> = {
  base_color: ["base_color", "base_colour", "basecolor", "albedo", "diffuse", "color"],
  normal: ["normal"],
  roughness: ["roughness"],
  metallic: ["metallic", "metalness"],
  ao: ["ao", "ambient_occlusion", "occlusion"],
  height: ["height", "displacement", "bump"],
  alpha: ["alpha", "opacity"],
  orm: ["orm", "arm"],
};

const PBR_COMMAND = "material_pbr";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function propertiesOf(schema: JsonSchema | undefined): Record<string, JsonSchema> {
  const properties = schema?.["properties"];
  return isRecord(properties) ? (properties as Record<string, JsonSchema>) : {};
}

function requiredOf(schema: JsonSchema): string[] {
  const required = schema["required"];
  return Array.isArray(required) ? required.filter((name): name is string => typeof name === "string") : [];
}

async function findRecord(workspace: Workspace, request: ApplyRequest): Promise<LicenseRecord> {
  const types = request.type === undefined ? ASSET_TYPES : [request.type];
  const found: LicenseRecord[] = [];
  for (const type of types) {
    const record = await readLocal(workspace, type, request.id);
    if (record !== undefined) found.push(record);
  }
  const only = found[0];
  if (only === undefined) {
    const where = request.type === undefined ? `library/<type>/${request.id}` : assetFolderPath(request.type, request.id);
    throw new LibraryError("not_found", `${request.id} is not downloaded (no ${where}/LICENSE.json); download it first with library_download`);
  }
  if (found.length > 1) throw new LibraryError("refused", `${request.id} is downloaded as ${found.map((record) => record.type).join(" and ")}; give type`);
  return only;
}

function requireCommand(bridge: BridgeAccess, name: string, why: string): BridgeCommand {
  const command = bridge.commands.find((entry) => entry.name === name);
  if (command === undefined) throw new LibraryError("failed", `${why} needs the bridge command ${name}, which this Blender does not offer`);
  return command;
}

const KIND: Record<AssetType, string> = { hdri: "an HDRI", texture: "a texture", model: "a model" };

function refuseFields(fields: string[], owner: AssetType, record: LicenseRecord): void {
  if (fields.length === 0 || record.type === owner) return;
  const verb = fields.length === 1 ? "applies" : "apply";
  throw new LibraryError("refused", `${fields.join(" and ")} ${verb} only to ${KIND[owner]}, and ${record.asset} is ${KIND[record.type]}`);
}

function checkFields(record: LicenseRecord, request: ApplyRequest): void {
  refuseFields((["strength", "rotation"] as const).filter((key) => request[key] !== undefined), "hdri", record);
  refuseFields((["object", "material"] as const).filter((key) => request[key] !== undefined), "texture", record);
}

async function run(bridge: BridgeAccess, workspace: Workspace, command: BridgeCommand, args: BridgeArgs, applied: Applied): Promise<Record<string, unknown>> {
  const outcome = await bridge.request(command.name, confineArgs(command, args, workspace));
  applied.steps.push({ command: command.name, result: outcome.result });
  applied.notices.push(...outcome.notices);
  return outcome.result;
}

function takesPath(schema: JsonSchema | undefined, named: string): boolean {
  if (schema === undefined) return false;
  if (schema["type"] === "string") return named.endsWith("_path") || schema["format"] === "path";
  return schema["type"] === "object" && propertiesOf(schema)["path"] !== undefined;
}

const CONVENTION_OF_MAP: Record<string, string> = { nor_gl: "opengl", nor_dx: "directx" };

function conventionIn(schema: JsonSchema | undefined, wanted: string | undefined): string | undefined {
  const options = schema?.["enum"];
  if (wanted === undefined || schema?.["type"] !== "string" || !Array.isArray(options)) return undefined;
  return options.find((entry): entry is string => typeof entry === "string" && entry.toLowerCase() === wanted);
}

function pathValue(schema: JsonSchema, absolute: string, map: string): unknown {
  if (schema["type"] === "string") return absolute;
  const value: Record<string, unknown> = { path: absolute };
  const convention = conventionIn(propertiesOf(schema)["convention"], CONVENTION_OF_MAP[map]);
  if (convention !== undefined) value["convention"] = convention;
  return value;
}

function slot(properties: Record<string, JsonSchema>, role: Role): string | undefined {
  for (const name of ROLE_NAMES[role]) {
    for (const candidate of [`${name}_path`, name]) if (takesPath(properties[candidate], candidate)) return candidate;
  }
  return undefined;
}

export function materialPbrArgs(command: BridgeCommand, record: LicenseRecord, workspace: Workspace, material: string, object: string | undefined): { args: BridgeArgs; notWired: string[]; assignsObject: boolean } {
  const top = propertiesOf(command.inputSchema);
  const nestedName = ["maps", "textures"].find((name) => top[name]?.["type"] === "object" && Object.keys(propertiesOf(top[name])).length > 0);
  const container = nestedName === undefined ? top : propertiesOf(top[nestedName]);
  const maps: BridgeArgs = {};
  const notWired: string[] = [];
  const folder = assetFolderPath(record.type, record.asset);
  const separateData = Object.keys(record.maps ?? {}).some((map) => ROLE_OF_MAP[map] === "roughness" || ROLE_OF_MAP[map] === "metallic");
  for (const [map, file] of Object.entries(record.maps ?? {})) {
    const role = ROLE_OF_MAP[map] === "orm" && separateData ? undefined : ROLE_OF_MAP[map];
    const name = role === undefined ? undefined : slot(container, role);
    const schema = name === undefined ? undefined : container[name];
    const value = role === undefined || schema === undefined ? undefined : pathValue(schema, workspace.resolve(`${folder}/${file}`), map);
    if (name === undefined || value === undefined || maps[name] !== undefined) notWired.push(map);
    else maps[name] = value;
  }
  if (Object.keys(maps).length === 0) {
    throw new LibraryError("failed", `${PBR_COMMAND} takes ${Object.keys(container).join(", ")}, and none of them fits the downloaded maps ${Object.keys(record.maps ?? {}).join(", ")}`);
  }
  const args: BridgeArgs = nestedName === undefined ? { ...maps } : { [nestedName]: maps };
  const normalMap = Object.keys(record.maps ?? {}).find((map) => ROLE_OF_MAP[map] === "normal" && !notWired.includes(map));
  const convention = conventionIn(top["normal_convention"], normalMap === undefined ? undefined : CONVENTION_OF_MAP[normalMap]);
  if (convention !== undefined) args["normal_convention"] = convention;
  const nameField = ["name", "material"].find((field) => top[field]?.["type"] === "string");
  if (nameField !== undefined) args[nameField] = material;
  let assignsObject = false;
  if (object !== undefined && top["object"]?.["type"] === "string") {
    args["object"] = object;
    assignsObject = true;
  } else if (object !== undefined && top["objects"]?.["type"] === "array") {
    args["objects"] = [object];
    assignsObject = true;
  }
  const missing = requiredOf(command.inputSchema).filter((field) => args[field] === undefined);
  if (missing.length > 0) throw new LibraryError("failed", `${PBR_COMMAND} requires ${missing.join(", ")}, which library_apply cannot fill from a texture set`);
  return { args, notWired, assignsObject };
}

async function applyTexture(bridge: BridgeAccess, workspace: Workspace, record: LicenseRecord, request: ApplyRequest, applied: Applied): Promise<void> {
  const command = bridge.commands.find((entry) => entry.name === PBR_COMMAND);
  if (command === undefined) {
    throw new LibraryError(
      "failed",
      `building a material from a texture set needs the bridge command ${PBR_COMMAND}, which this Blender does not offer yet; the maps are downloaded in ${assetFolderPath("texture", record.asset)}/`,
    );
  }
  const material = request.material ?? record.asset;
  const { args, notWired, assignsObject } = materialPbrArgs(command, record, workspace, material, request.object);
  const result = await run(bridge, workspace, command, args, applied);
  if (notWired.length > 0) applied.notWired = notWired;
  if (request.object !== undefined && !assignsObject) {
    const assign = requireCommand(bridge, "assign_material", "giving the object the material");
    const made = [result["material"], result["name"]].find((value): value is string => typeof value === "string") ?? material;
    await run(bridge, workspace, assign, { name: request.object, material: made }, applied);
  }
}

export async function applyAsset(bridge: BridgeAccess, workspace: Workspace, request: ApplyRequest): Promise<Applied> {
  const record = await findRecord(workspace, request);
  checkFields(record, request);
  const problem = await verifyLocal(workspace, record);
  if (problem !== undefined) throw new LibraryError("invalid", `${assetFolderPath(record.type, record.asset)} is incomplete (${problem}); download it again`);
  const applied: Applied = { record, steps: [], notices: [] };
  const folder = assetFolderPath(record.type, record.asset);
  if (record.type !== "texture" && record.main === undefined) throw new LibraryError("invalid", `${folder}/LICENSE.json names no main file; download the asset again`);
  if (record.type === "hdri") {
    const command = requireCommand(bridge, "set_world_hdri", "lighting the scene with an HDRI");
    const args: BridgeArgs = { path: `${folder}/${record.main}` };
    if (request.strength !== undefined) args["strength"] = request.strength;
    if (request.rotation !== undefined) args["rotation"] = request.rotation;
    await run(bridge, workspace, command, args, applied);
  } else if (record.type === "model") {
    const command = requireCommand(bridge, "import", "importing a model");
    await run(bridge, workspace, command, { path: `${folder}/${record.main}` }, applied);
  } else {
    await applyTexture(bridge, workspace, record, request, applied);
  }
  return applied;
}
