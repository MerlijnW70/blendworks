import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { BLENDER_VERSION } from "../blender.js";

const run = promisify(execFile);

export class BlenderVersionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BlenderVersionError";
  }
}

export function parseBlenderVersion(output: string): string | undefined {
  return /^Blender (\d+\.\d+\.\d+)/m.exec(output)?.[1];
}

export function checkBlenderVersion(output: string): string {
  const version = parseBlenderVersion(output);
  if (version === undefined) throw new BlenderVersionError("cannot read the Blender version; is BLENDER a Blender binary?");
  const [major, minor] = version.split(".");
  if (`${major}.${minor}` !== BLENDER_VERSION) {
    throw new BlenderVersionError(`Blender ${version} is not supported; the judge needs Blender ${BLENDER_VERSION}`);
  }
  return version;
}

export async function blenderVersion(blender: string): Promise<string> {
  let output: string;
  try {
    ({ stdout: output } = await run(blender, ["--background", "--factory-startup", "--version"], { timeout: 60_000, windowsHide: true }));
  } catch (error) {
    throw new BlenderVersionError(`cannot run Blender at ${blender}: ${(error as Error).message.split("\n")[0]}`);
  }
  return checkBlenderVersion(output);
}
