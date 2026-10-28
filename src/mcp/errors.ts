export const SCHEMA_ECHO_CHARS = 1200;
export const PROBLEMS_SHOWN = 10;

export function badArguments(name: string, problems: string[], schema: unknown): string {
  const echo = JSON.stringify(schema);
  const shown = echo.length > SCHEMA_ECHO_CHARS ? `${echo.slice(0, SCHEMA_ECHO_CHARS)}... [cut: the schema has ${echo.length} characters; blender_find_tools with the name ${name} shows the rest]` : echo;
  const more = problems.length > PROBLEMS_SHOWN ? `; and ${problems.length - PROBLEMS_SHOWN} more` : "";
  return `bad_args: ${name} refused these arguments: ${problems.slice(0, PROBLEMS_SHOWN).join("; ")}${more}. Its schema: ${shown}`;
}

export const START_HINT =
  "Set BLENDER to the full path of a working Blender (npm run doctor shows what is found), then call again: the server tries to start it again on the next call. If that does not help, restart the MCP server.";
