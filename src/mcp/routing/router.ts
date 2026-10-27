import type { CallToolResult, Tool } from "@modelcontextprotocol/sdk/types.js";
import type { Route } from "./catalog.js";
import { exampleCall } from "./examples.js";
import { CALL_TOOL, PYTHON_TOOL, SEARCH_TOOL } from "./names.js";
import type { ToolSearch } from "./search.js";
import type { Workflow } from "./workflows.js";

export const DEFAULT_LIMIT = 5;
export const MAX_LIMIT = 10;
const BUILT_IN_LIMIT = 3;
const OUTSIDE_LIMIT = 2;
const MAX_TEXT = 300;

export interface FindArgs {
  query?: string;
  goal?: string;
  families?: string[];
  limit: number;
}

export interface Found {
  result: CallToolResult;
  names: string[];
}

export function routerTools(families: string[]): Tool[] {
  return [
    {
      name: SEARCH_TOOL,
      description: `Find the Blender tools for a task when the one you need is not listed: query by intent ("round the edges", "cut text into a ring") returns the best tools with their full schemas and an example call; goal ("engraved brass dial", "rock set") returns a workflow's tool sequence. Then call a tool by name, or through ${CALL_TOOL}.`,
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          query: { type: "string", description: "What you want to do, in plain words.", minLength: 1, maxLength: MAX_TEXT },
          goal: { type: "string", description: "The asset or result you are building, for a whole workflow.", minLength: 1, maxLength: MAX_TEXT },
          families: { type: "array", description: "Only search these tool families.", items: { type: "string", enum: families }, minItems: 1, maxItems: families.length },
          limit: { type: "integer", description: "Number of tools to return.", minimum: 1, maximum: MAX_LIMIT, default: DEFAULT_LIMIT },
        },
      },
      annotations: { title: "Find Blender tools", readOnlyHint: true, idempotentHint: true, destructiveHint: false, openWorldHint: false },
    },
    {
      name: CALL_TOOL,
      description: `Call a Blendworks tool that your client does not list, by name, with its arguments as an object. Find the tool and its schema with ${SEARCH_TOOL} first; arguments that do not match the schema are refused with the schema.`,
      inputSchema: {
        type: "object",
        additionalProperties: false,
        required: ["tool"],
        properties: {
          tool: { type: "string", description: "The tool's name, such as blender_bevel.", minLength: 1, maxLength: 128 },
          arguments: { type: "object", description: "The tool's arguments, as its schema describes them." },
        },
      },
      annotations: { title: "Call a Blendworks tool", readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
    },
  ];
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim().slice(0, MAX_TEXT) : undefined;
}

export function readFindArgs(args: Record<string, unknown>, known: Set<string>): FindArgs | string {
  const unknown = Object.keys(args).filter((key) => !["query", "goal", "families", "limit"].includes(key));
  if (unknown.length > 0) return `unknown fields ${unknown.join(", ")}`;
  const query = text(args["query"]);
  const goal = text(args["goal"]);
  if (query === undefined && goal === undefined) return "give a query, a goal, or both";
  const families = Array.isArray(args["families"]) ? args["families"].filter((family): family is string => typeof family === "string") : undefined;
  const strange = (families ?? []).filter((family) => !known.has(family));
  if (strange.length > 0) return `unknown families ${strange.join(", ")}; the families are ${[...known].sort().join(", ")}`;
  const rawLimit = args["limit"] ?? DEFAULT_LIMIT;
  if (typeof rawLimit !== "number" || !Number.isInteger(rawLimit) || rawLimit < 1 || rawLimit > MAX_LIMIT) return `limit must be a whole number from 1 to ${MAX_LIMIT}`;
  return { ...(query === undefined ? {} : { query }), ...(goal === undefined ? {} : { goal }), ...(families === undefined ? {} : { families }), limit: rawLimit };
}

function toolBlock(index: number, route: Route): string {
  return [
    `${index}. ${route.name} (${route.family}): ${route.tool.description ?? ""}`,
    `   Example: ${exampleCall(route.name, route.tool.inputSchema as Record<string, unknown>)}`,
    `   Schema: ${JSON.stringify(route.tool.inputSchema)}`,
  ].join("\n");
}

function workflowBlock(workflow: Workflow, routes: Map<string, Route>): string {
  const steps = workflow.steps.map((name, index) => {
    const route = routes.get(name);
    if (route === undefined) return `${index + 1}. ${name}: not offered by this Blender`;
    return `${index + 1}. ${name}: ${route.summary} Example: ${exampleCall(name, route.tool.inputSchema as Record<string, unknown>)}`;
  });
  return [`Workflow "${workflow.goal}": ${workflow.steps.join(" > ")}.`, workflow.note, ...steps].join("\n");
}

export function find(search: ToolSearch, args: FindArgs): Found {
  const routes = new Map(search.routes.map((route) => [route.name, route]));
  const sections: string[] = [];
  const names: string[] = [];
  if (args.goal !== undefined) {
    const matched = search.goal(args.goal);
    if (matched === undefined) sections.push(`No workflow matches the goal "${args.goal}".`);
    else {
      sections.push(workflowBlock(matched.workflow, routes));
      names.push(...matched.workflow.steps.filter((name) => routes.has(name)));
    }
  }
  const query = args.query ?? (args.goal !== undefined && names.length === 0 ? args.goal : undefined);
  if (query !== undefined) {
    const matches = search.search(query, { limit: args.limit, ...(args.families === undefined ? {} : { families: args.families }) });
    if (matches.length === 0) sections.push(`No tool matches "${query}". Try other words, or a goal.`);
    else {
      sections.push(`Tools for "${query}", best first:\n${matches.map((match, index) => toolBlock(index + 1, routes.get(match.name)!)).join("\n")}`);
      names.push(...matches.map((match) => match.name));
    }
    if (args.families !== undefined) {
      const chosen = new Set(args.families);
      const weakest = matches.at(-1)?.score ?? 0;
      const outside = search.search(query).filter((match) => !chosen.has(routes.get(match.name)!.family) && match.score >= weakest).slice(0, OUTSIDE_LIMIT);
      if (outside.length > 0) {
        sections.push(`Better matches outside ${args.families.join(", ")}:\n${outside.map((match, index) => toolBlock(index + 1, routes.get(match.name)!)).join("\n")}`);
        names.push(...outside.map((match) => match.name));
      }
    }
    if (matches.some((match) => match.name === PYTHON_TOOL)) {
      const shown = new Set(matches.map((match) => match.name));
      const builtIn = search.search(query).filter((match) => match.name !== PYTHON_TOOL && !shown.has(match.name)).slice(0, BUILT_IN_LIMIT);
      if (builtIn.length > 0) {
        sections.push(`${PYTHON_TOOL} is the last resort. Built-in tools that may do this without code:\n${builtIn.map((match, index) => toolBlock(index + 1, routes.get(match.name)!)).join("\n")}`);
        names.push(...builtIn.map((match) => match.name));
      }
    }
  }
  sections.push(`Call a tool by its name if your client lists it, or through ${CALL_TOOL} {"tool": "<name>", "arguments": {...}}.`);
  return { result: { content: [{ type: "text", text: sections.join("\n\n") }] }, names: [...new Set(names)] };
}
