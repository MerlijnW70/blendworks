import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { bagOf, Bm25Index } from "../../src/mcp/routing/bm25.js";
import { tokens } from "../../src/mcp/routing/text.js";
import type { Ranker } from "./metrics.js";

export function baselineRanker(tools: Tool[]): Ranker {
  const index = new Bm25Index();
  for (const tool of tools) index.add(tool.name, [{ tokens: tokens(tool.name.replace(/_/g, " ")), weight: 1 }, { tokens: tokens(tool.description ?? ""), weight: 1 }]);
  return (query) => index.score(bagOf(tokens(query))).map((entry) => entry.key);
}
