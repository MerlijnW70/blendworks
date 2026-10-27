export const SEARCH_TOOL = "blender_find_tools";
export const CALL_TOOL = "blender_call";
export const PYTHON_TOOL = "blender_run_python";
export const BRIDGE_PREFIX = "blender_";
export const LIBRARY_FAMILY = "library";
export const ROUTER_FAMILY = "routing";

export function toolNameOf(name: string): string {
  if (name.startsWith(`${BRIDGE_PREFIX}library_`)) return name.slice(BRIDGE_PREFIX.length);
  return name.startsWith("library_") || name.startsWith(BRIDGE_PREFIX) ? name : `${BRIDGE_PREFIX}${name}`;
}
