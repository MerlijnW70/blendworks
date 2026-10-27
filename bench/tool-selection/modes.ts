import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { LIBRARY_TOOLS } from "../../src/mcp/library/tools.js";
import { libraryTool, routesFor } from "../../src/mcp/routing/catalog.js";
import { SEARCH_TOOL } from "../../src/mcp/routing/names.js";
import { ToolSearch } from "../../src/mcp/routing/search.js";
import type { BridgeCommand } from "../../src/mcp/schema.js";
import type { ServerParts } from "../../src/mcp/server.js";
import { buildTools } from "../../src/mcp/tools.js";
import type { Ranker } from "./metrics.js";

export interface Mode {
  full: Partial<ServerParts>;
  parts: Partial<ServerParts>;
  ranker?: (commands: BridgeCommand[]) => Ranker;
}

export function productSearch(commands: BridgeCommand[]): ToolSearch {
  return new ToolSearch(routesFor(buildTools(commands), LIBRARY_TOOLS.map(libraryTool)));
}

export function productRanker(commands: BridgeCommand[]): Ranker {
  const search = productSearch(commands);
  return (query) => search.search(query).map((match) => match.name);
}

export function legacyListing(tools: Tool[]): Tool[] {
  return tools
    .filter((tool) => tool.name !== SEARCH_TOOL)
    .map((tool) => {
      const { _meta: _dropped, ...rest } = tool;
      return { ...rest, description: (tool.description ?? "").replace(/ Instead: [^]*$/, "") };
    });
}

const ALL: Partial<ServerParts> = { toolsets: { kind: "all" } };

export const MODES: Record<string, Mode> = {
  core: { full: ALL, parts: { toolsets: { kind: "core", families: [] } }, ranker: productRanker },
  all: { full: ALL, parts: ALL },
};
