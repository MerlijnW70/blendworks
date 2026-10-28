import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { Route } from "./catalog.js";
import { chooseCore, CORE_PINNED } from "./core.js";
import { CORE_FILL } from "./core.generated.js";
import { CALL_TOOL, SEARCH_TOOL } from "./names.js";

export type Toolsets = { kind: "auto" } | { kind: "all" } | { kind: "core"; families: string[] };
export type ResolvedToolsets = { kind: "all"; reason: string } | { kind: "core"; families: string[]; reason: string };

export const TOOLSETS_USAGE = "auto, all, core, or core plus families as a comma list (for example core,uv,materials)";
export const CLIENTS_WITH_TOOL_SEARCH = new Set(["claude-code"]);
export const ALWAYS_LOAD_META = "anthropic/alwaysLoad";
export const MAX_ACTIVATED = 24;

export function parseToolsets(value: string): Toolsets {
  const parts = value
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
  if (parts.length === 0) throw new Error(`--toolsets needs a value: ${TOOLSETS_USAGE}`);
  if (parts.length === 1 && parts[0] === "auto") return { kind: "auto" };
  if (parts.length === 1 && parts[0] === "all") return { kind: "all" };
  if (parts.includes("all") || parts.includes("auto")) throw new Error(`--toolsets ${value}: all and auto stand alone; use ${TOOLSETS_USAGE}`);
  for (const part of parts) if (!/^[a-z][a-z0-9_]*$/.test(part)) throw new Error(`--toolsets ${value}: "${part}" is not a family name`);
  return { kind: "core", families: [...new Set(parts.filter((part) => part !== "core"))] };
}

export function resolveToolsets(toolsets: Toolsets, clientName: string | undefined): ResolvedToolsets {
  if (toolsets.kind === "all") return { kind: "all", reason: "--toolsets all" };
  if (toolsets.kind === "core") return { kind: "core", families: toolsets.families, reason: "--toolsets" };
  if (clientName !== undefined && CLIENTS_WITH_TOOL_SEARCH.has(clientName)) return { kind: "all", reason: `${clientName} searches deferred tools itself` };
  return { kind: "core", families: [], reason: "the default for clients without their own tool search" };
}

export function unknownFamilies(toolsets: Toolsets, routes: Route[]): string[] {
  if (toolsets.kind !== "core") return [];
  const known = new Set(routes.map((route) => route.family));
  return toolsets.families.filter((family) => !known.has(family));
}

function toolBytes(tool: Tool): number {
  return Buffer.byteLength(JSON.stringify(tool), "utf8");
}

export function toolSizes(routes: Route[]): Map<string, number> {
  return new Map(routes.map((route) => [route.name, toolBytes(route.tool)]));
}

export function coreNames(routes: Route[]): string[] {
  return chooseCore(CORE_PINNED, CORE_FILL, toolSizes(routes));
}

export class Disclosure {
  readonly core: string[];
  private readonly activated: string[] = [];
  private readonly byName: Map<string, Route>;

  constructor(
    readonly routes: Route[],
    readonly routerTools: Tool[],
  ) {
    this.core = coreNames(routes);
    this.byName = new Map(routes.map((route) => [route.name, route]));
  }

  has(name: string): boolean {
    return this.byName.has(name);
  }

  route(name: string): Route | undefined {
    return this.byName.get(name);
  }

  listedNames(resolved: ResolvedToolsets): Set<string> {
    if (resolved.kind === "all") return new Set(this.routes.map((route) => route.name));
    const families = new Set(resolved.families);
    return new Set([...this.core, ...this.routes.filter((route) => families.has(route.family)).map((route) => route.name), ...this.activated]);
  }

  listing(resolved: ResolvedToolsets): Tool[] {
    const names = this.listedNames(resolved);
    const core = new Set(this.core);
    const tools = this.routes
      .filter((route) => names.has(route.name))
      .map((route) => (resolved.kind === "all" && core.has(route.name) ? { ...route.tool, _meta: { ...(route.tool._meta ?? {}), [ALWAYS_LOAD_META]: true } } : route.tool));
    const router = this.routerTools.filter((tool) => resolved.kind === "core" || tool.name === SEARCH_TOOL);
    return [...router, ...tools];
  }

  activate(names: string[], resolved: ResolvedToolsets): boolean {
    if (resolved.kind === "all") return false;
    const before = this.listedNames(resolved);
    for (const name of names) {
      if (!this.byName.has(name) || name === CALL_TOOL || name === SEARCH_TOOL) continue;
      const index = this.activated.indexOf(name);
      if (index >= 0) this.activated.splice(index, 1);
      this.activated.push(name);
    }
    while (this.activated.length > MAX_ACTIVATED) this.activated.shift();
    const after = this.listedNames(resolved);
    return after.size !== before.size || [...after].some((name) => !before.has(name));
  }
}
