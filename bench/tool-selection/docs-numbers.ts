import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { buildInstructions, WORKSPACE_RESERVE } from "../../src/mcp/instructions.js";
import { CALL_TOOL, SEARCH_TOOL } from "../../src/mcp/routing/names.js";
import type { Intent } from "./intents.js";
import { estimateTokens, listingBytes } from "./metrics.js";

export const DESIGN_FILE = fileURLToPath(new URL("../../docs/DESIGN.md", import.meta.url));
export const NUMBERS_START = "<!-- numbers: printed by npm run bench:tools, checked by test/mcp-routing-bench.test.ts -->";
export const NUMBERS_END = "<!-- end of numbers -->";
export const DOCS_COMMAND = "npm run bench:tools -- --docs";

export interface Figure {
  label: string;
  value: string;
}

export interface Listings {
  all: Tool[];
  core: Tool[];
  intents: Intent[];
}

export function grouped(value: number): string {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function aboutThousands(value: number): string {
  return `about ${grouped(Math.round(value / 1000) * 1000)}`;
}

export function docsFigures({ all, core, intents }: Listings): Figure[] {
  const routers = new Set([SEARCH_TOOL, CALL_TOOL]);
  const tools = all.filter((tool) => !routers.has(tool.name));
  const coreTools = core.filter((tool) => !routers.has(tool.name));
  const instructions = buildInstructions(`/${"w".repeat(WORKSPACE_RESERVE - 1)}`);
  return [
    { label: "Tools (bridge commands and library tools)", value: grouped(tools.length) },
    { label: "Tools in the default core listing", value: grouped(coreTools.length) },
    { label: "Full listing, tokens", value: aboutThousands(estimateTokens(listingBytes(all))) },
    { label: "Default listing, tokens", value: aboutThousands(estimateTokens(listingBytes(core))) },
    { label: "Benchmark intents", value: grouped(intents.length) },
    { label: "Held-out intents", value: grouped(intents.filter((intent) => intent.split === "heldout").length) },
    { label: "Instructions with a 200-character workspace path, characters", value: grouped(instructions.text.length) },
    { label: "Tier 0 of the instructions, characters", value: grouped(instructions.tier0) },
    { label: "Tier 1 lines dropped for the budget", value: instructions.dropped.length === 0 ? "none" : instructions.dropped.join(", ") },
    { label: "Longest tool description, characters", value: grouped(Math.max(...all.map((tool) => (tool.description ?? "").length))) },
  ];
}

export function numbersTable(figures: Figure[]): string {
  return [NUMBERS_START, "| Figure | Value |", "|---|---|", ...figures.map((figure) => `| ${figure.label} | ${figure.value} |`), NUMBERS_END].join("\n");
}

export function quotedFigures(markdown: string): Map<string, string> {
  const start = markdown.indexOf(NUMBERS_START);
  const end = markdown.indexOf(NUMBERS_END);
  const quoted = new Map<string, string>();
  if (start < 0 || end < start) return quoted;
  for (const line of markdown.slice(start, end).split("\n")) {
    const cells = /^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$/.exec(line.trim());
    if (cells !== null && cells[1] !== "Figure" && !/^-+$/.test(cells[1]!)) quoted.set(cells[1]!, cells[2]!);
  }
  return quoted;
}

export function staleFigures(markdown: string, figures: Figure[]): string[] {
  const quoted = quotedFigures(markdown);
  const problems: string[] = [];
  for (const figure of figures) {
    const said = quoted.get(figure.label);
    if (said === undefined) problems.push(`docs/DESIGN.md does not quote "${figure.label}" (${figure.value})`);
    else if (said !== figure.value) problems.push(`docs/DESIGN.md says "${figure.label}" is ${said}, but npm run bench:tools prints ${figure.value}`);
  }
  for (const label of quoted.keys()) if (!figures.some((figure) => figure.label === label)) problems.push(`docs/DESIGN.md quotes "${label}", which npm run bench:tools no longer prints`);
  return problems;
}

export function withFigures(markdown: string, figures: Figure[]): string {
  const start = markdown.indexOf(NUMBERS_START);
  const end = markdown.indexOf(NUMBERS_END);
  if (start < 0 || end < start) throw new Error(`docs/DESIGN.md has no numbers table between "${NUMBERS_START}" and "${NUMBERS_END}"`);
  return markdown.slice(0, start) + numbersTable(figures) + markdown.slice(end + NUMBERS_END.length);
}

export function writeDocsFigures(figures: Figure[], file: string = DESIGN_FILE): void {
  writeFileSync(file, withFigures(readFileSync(file, "utf8"), figures));
}
