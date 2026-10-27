import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { Nearest } from "../schema.js";
import type { ToolEntry } from "../tools.js";
import { LIBRARY_FAMILY, toolNameOf } from "./names.js";

export interface Route {
  name: string;
  family: string;
  summary: string;
  intents: string[];
  nearest: Nearest[];
  tool: Tool;
  command: string | undefined;
}

export const UNSORTED_FAMILY = "unsorted";

interface LibraryRouting {
  intents: string[];
  nearest: Nearest[];
}

export const LIBRARY_ROUTING: Record<string, LibraryRouting> = {
  library_search: {
    intents: ["find a free HDRI, texture or model on Poly Haven", "search CC0 assets online"],
    nearest: [{ name: "library_apply", when: "once you know the asset id" }],
  },
  library_preview: {
    intents: ["see a Poly Haven asset's thumbnail before downloading"],
    nearest: [{ name: "library_search", when: "to find assets" }],
  },
  library_download: {
    intents: ["download a Poly Haven HDRI, texture set or model at a resolution"],
    nearest: [{ name: "library_apply", when: "to download and use it in one step" }],
  },
  library_apply: {
    intents: ["light the scene with a Poly Haven HDRI", "turn a Poly Haven texture set into a material on an object", "import a Poly Haven model"],
    nearest: [
      { name: "material_pbr", when: "for your own image files" },
      { name: "set_world_hdri", when: "for an HDRI file in the workspace" },
    ],
  },
};

export function nearestSentence(nearest: Nearest[]): string {
  if (nearest.length === 0) return "";
  return `Instead: ${nearest.map((entry) => `${toolNameOf(entry.name)} ${entry.when}`).join("; ")}.`;
}

export function withNearest(description: string, nearest: Nearest[]): string {
  const sentence = nearestSentence(nearest);
  return sentence === "" ? description : `${description} ${sentence}`;
}

export function libraryTool(tool: Tool): Tool {
  const routing = LIBRARY_ROUTING[tool.name];
  return routing === undefined ? tool : { ...tool, description: withNearest(tool.description ?? "", routing.nearest) };
}

export function routesFor(bridgeTools: Map<string, ToolEntry>, libraryTools: Tool[]): Route[] {
  const routes: Route[] = [];
  for (const [name, entry] of bridgeTools) {
    routes.push({
      name,
      family: entry.command.family ?? UNSORTED_FAMILY,
      summary: entry.command.description,
      intents: entry.command.intents,
      nearest: entry.command.nearest,
      tool: entry.tool,
      command: entry.command.name,
    });
  }
  for (const tool of libraryTools) {
    const routing = LIBRARY_ROUTING[tool.name] ?? { intents: [], nearest: [] };
    const original = tool.description ?? "";
    const sentence = nearestSentence(routing.nearest);
    const summary = sentence !== "" && original.endsWith(sentence) ? original.slice(0, -sentence.length).trim() : original;
    routes.push({ name: tool.name, family: LIBRARY_FAMILY, summary, intents: routing.intents, nearest: routing.nearest, tool, command: undefined });
  }
  return routes;
}

export function familiesOf(routes: Route[]): Map<string, string[]> {
  const families = new Map<string, string[]>();
  for (const route of routes) families.set(route.family, [...(families.get(route.family) ?? []), route.name]);
  return families;
}
