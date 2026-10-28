import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { libraryTool, routesFor } from "./routing/catalog.js";
import { Disclosure, type Toolsets, TOOLSETS_USAGE, unknownFamilies } from "./routing/disclosure.js";
import { routerTools } from "./routing/router.js";
import { ToolSearch } from "./routing/search.js";
import { ArgumentCheck } from "./routing/validate.js";
import type { BridgeCommand } from "./schema.js";
import { buildTools, listTools, type ToolEntry } from "./tools.js";

export interface Surface {
  commands: BridgeCommand[];
  tools: Map<string, ToolEntry>;
  families: string[];
  disclosure: Disclosure;
  search: ToolSearch;
  check: ArgumentCheck;
}

export function buildSurface(commands: BridgeCommand[], libraryTools: Tool[], toolsets: Toolsets): Surface {
  const tools = buildTools(commands);
  const library = libraryTools.map(libraryTool);
  listTools(tools, library);
  const routes = routesFor(tools, library);
  const strange = commands.length === 0 ? [] : unknownFamilies(toolsets, routes);
  if (strange.length > 0) {
    throw new Error(`--toolsets names unknown families ${strange.join(", ")}; use ${TOOLSETS_USAGE}, with the families ${[...new Set(routes.map((route) => route.family))].sort().join(", ")}`);
  }
  const families = [...new Set(routes.map((route) => route.family))].sort();
  return {
    commands,
    tools,
    families,
    disclosure: new Disclosure(routes, routerTools(families)),
    search: new ToolSearch(routes),
    check: new ArgumentCheck(new Map(routes.map((route) => [route.name, route.tool.inputSchema]))),
  };
}
