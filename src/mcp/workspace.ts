import { existsSync, mkdirSync, realpathSync } from "node:fs";
import { basename, dirname, isAbsolute, relative, resolve, sep } from "node:path";

export const DEFAULT_WORKSPACE = "workspace";

export class WorkspaceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkspaceError";
  }
}

function comparable(path: string): string {
  return process.platform === "win32" ? path.toLowerCase() : path;
}

function contains(root: string, path: string): boolean {
  const rel = relative(comparable(root), comparable(path));
  return rel === "" || (!isAbsolute(rel) && rel !== ".." && !rel.startsWith(`..${sep}`));
}

function realOfDeepestExisting(path: string): string {
  let existing = path;
  const missing: string[] = [];
  while (!existsSync(existing)) {
    const parent = dirname(existing);
    if (parent === existing) break;
    missing.unshift(basename(existing));
    existing = parent;
  }
  const real = existsSync(existing) ? realpathSync.native(existing) : existing;
  return missing.length === 0 ? real : resolve(real, ...missing);
}

export class Workspace {
  private constructor(readonly root: string) {}

  static open(dir: string, cwd: string = process.cwd()): Workspace {
    const absolute = resolve(cwd, dir);
    mkdirSync(absolute, { recursive: true });
    return new Workspace(realpathSync.native(absolute));
  }

  resolve(clientPath: unknown): string {
    if (typeof clientPath !== "string" || clientPath.trim() === "") {
      throw new WorkspaceError("a path must be a non-empty string");
    }
    if (clientPath.includes("\0")) throw new WorkspaceError("a path must not contain a NUL character");
    const absolute = resolve(this.root, clientPath);
    if (!contains(this.root, absolute) || !contains(this.root, realOfDeepestExisting(absolute))) {
      throw new WorkspaceError(`"${clientPath}" is outside the workspace ${this.root}; use a path inside it, such as "crate.glb"`);
    }
    return absolute;
  }
}
