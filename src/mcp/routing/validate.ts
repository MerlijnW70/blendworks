import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

type Parser = z.ZodType;

export class ArgumentCheck {
  private readonly parsers = new Map<string, Parser>();

  constructor(private readonly schemas: Map<string, Tool["inputSchema"]>) {}

  private parser(name: string): Parser | undefined {
    const cached = this.parsers.get(name);
    if (cached !== undefined) return cached;
    const schema = this.schemas.get(name);
    if (schema === undefined) return undefined;
    const parser = z.fromJSONSchema(schema as Parameters<typeof z.fromJSONSchema>[0]);
    this.parsers.set(name, parser);
    return parser;
  }

  problems(name: string, args: Record<string, unknown>): string[] {
    const parser = this.parser(name);
    if (parser === undefined) return [`${name} is not a tool of this server`];
    const result = parser.safeParse(args);
    if (result.success) return [];
    return result.error.issues.map((issue) => {
      const where = issue.path.length === 0 ? "arguments" : issue.path.map(String).join(".");
      return `${where}: ${issue.message}`;
    });
  }
}
