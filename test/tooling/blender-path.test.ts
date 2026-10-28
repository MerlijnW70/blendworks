import { posix, win32 } from "node:path";
import { describe, expect, it } from "vitest";
import {
  BLENDER_DOWNLOAD_URL,
  BLENDER_VERSION,
  BlenderNotFoundError,
  defaultBlenderLocations,
  resolveBlender,
} from "../../src/blender.js";

const HOME = posix.join("/home", "dev");
const WINDOWS_HOME = "C:\\Users\\dev";

function only(...present: string[]): (path: string) => boolean {
  return (path) => present.includes(path);
}

describe("resolving Blender", () => {
  it("uses BLENDER first, even when a default location exists", () => {
    const defaults = defaultBlenderLocations("linux", {}, HOME);
    const found = resolveBlender({ env: { BLENDER: "/custom/blender" }, platform: "linux", home: HOME, exists: only("/custom/blender", ...defaults) });
    expect(found).toEqual({ path: "/custom/blender", source: "BLENDER" });
  });

  it("takes the first default location that exists, in the platform's order", () => {
    const defaults = defaultBlenderLocations("linux", {}, HOME);
    const found = resolveBlender({ env: {}, platform: "linux", home: HOME, exists: only(defaults[2] as string, defaults[4] as string) });
    expect(found).toEqual({ path: defaults[2], source: "default location" });
  });

  it("falls back to blender on PATH after the default locations", () => {
    const onPath = posix.join("/usr/games", "blender");
    const found = resolveBlender({ env: { PATH: ["/bin", "/usr/games"].join(posix.delimiter) }, platform: "linux", home: HOME, exists: only(onPath) });
    expect(found).toEqual({ path: onPath, source: "PATH" });
  });

  it("looks for blender.exe on Windows, in Program Files, the user's programs and PATH", () => {
    const env = { ProgramFiles: "C:\\Program Files", LOCALAPPDATA: "C:\\Users\\dev\\AppData\\Local" };
    const defaults = defaultBlenderLocations("win32", env, "C:\\Users\\dev");
    expect(defaults[0]).toContain(`Blender ${BLENDER_VERSION}`);
    expect(defaults.every((path) => path.endsWith("blender.exe"))).toBe(true);
    expect(resolveBlender({ env, platform: "win32", home: "C:\\Users\\dev", exists: only(defaults[1] as string) }).path).toBe(defaults[1]);
  });

  it("falls back to C:\\Program Files when ProgramFiles is not set", () => {
    const defaults = defaultBlenderLocations("win32", {}, "C:\\Users\\dev");
    expect(defaults[0]?.startsWith("C:\\Program Files\\Blender Foundation")).toBe(true);
  });

  it("knows the macOS app bundle", () => {
    expect(defaultBlenderLocations("darwin", {}, HOME)[0]).toBe("/Applications/Blender.app/Contents/MacOS/Blender");
  });

  it("accepts a bare command name in BLENDER when it is on PATH", () => {
    const where = posix.join("/opt/tools", "blender-lts");
    const found = resolveBlender({ env: { BLENDER: "blender-lts", PATH: "/opt/tools" }, platform: "linux", home: HOME, exists: only(where) });
    expect(found).toEqual({ path: where, source: "BLENDER" });
  });

  it("builds Windows paths with Windows rules and Linux paths with POSIX rules, whatever the host", () => {
    const windows = defaultBlenderLocations("win32", { ProgramFiles: "C:\\Program Files", LOCALAPPDATA: "C:\\Users\\dev\\AppData\\Local" }, WINDOWS_HOME);
    expect(windows).toEqual([
      "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe",
      "C:\\Users\\dev\\AppData\\Local\\Programs\\Blender Foundation\\Blender 5.2\\blender.exe",
      "C:\\Users\\dev\\tools\\blender\\blender.exe",
    ]);
    expect(defaultBlenderLocations("win32", {}, WINDOWS_HOME)[1]).toBe("C:\\Users\\dev\\AppData\\Local\\Programs\\Blender Foundation\\Blender 5.2\\blender.exe");
    expect(defaultBlenderLocations("linux", {}, HOME)).toEqual(["/home/dev/tools/blender/blender", "/home/dev/blender/blender", "/opt/blender/blender", "/usr/local/bin/blender", "/usr/bin/blender", "/snap/bin/blender"]);
    expect(defaultBlenderLocations("darwin", {}, "/Users/dev")[1]).toBe("/Users/dev/Applications/Blender.app/Contents/MacOS/Blender");
  });

  it("splits PATH and joins its folders by the rules of the platform it looks on", () => {
    const windowsPath = { Path: ["C:\\Windows", "D:\\Apps\\Blender"].join(win32.delimiter) };
    expect(resolveBlender({ env: windowsPath, platform: "win32", home: WINDOWS_HOME, exists: only("D:\\Apps\\Blender\\blender.exe") })).toEqual({ path: "D:\\Apps\\Blender\\blender.exe", source: "PATH" });
    const linuxPath = { PATH: ["/bin", "/opt/c:d"].join(posix.delimiter) };
    expect(resolveBlender({ env: linuxPath, platform: "linux", home: HOME, exists: only("/opt/c/blender", "/opt/c:d/blender") }).path).toBe("/opt/c/blender");
  });

  it("takes a Windows path in BLENDER as a path on Windows and a bare name elsewhere", () => {
    expect(resolveBlender({ env: { BLENDER: "D:\\Blender\\blender.exe" }, platform: "win32", home: WINDOWS_HOME, exists: only("D:\\Blender\\blender.exe") })).toEqual({ path: "D:\\Blender\\blender.exe", source: "BLENDER" });
    expect(() => resolveBlender({ env: { BLENDER: "D:\\Blender\\blender.exe", PATH: "/bin" }, platform: "linux", home: HOME, exists: () => false })).toThrow(/which is not on PATH/);
  });

  it("holds no machine-specific path", () => {
    for (const os of ["win32", "linux", "darwin"] as const) {
      expect(defaultBlenderLocations(os, {}, HOME).join("\n")).not.toMatch(/\bF:/);
    }
  });
});

describe("the error when Blender is missing", () => {
  it("names the variable that points nowhere, instead of falling back to a default", () => {
    const defaults = defaultBlenderLocations("linux", {}, HOME);
    let caught: unknown;
    try {
      resolveBlender({ env: { BLENDER: "/does/not/exist" }, platform: "linux", home: HOME, exists: only(...defaults) });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(BlenderNotFoundError);
    const message = (caught as Error).message;
    expect(message).toContain("BLENDER is set to /does/not/exist, which does not exist");
    expect(message).toContain(BLENDER_DOWNLOAD_URL);
  });

  it("lists every place it looked and the download link when nothing is set", () => {
    let caught: BlenderNotFoundError | undefined;
    try {
      resolveBlender({ env: {}, platform: "linux", home: HOME, exists: () => false });
    } catch (error) {
      caught = error as BlenderNotFoundError;
    }
    expect(caught).toBeInstanceOf(BlenderNotFoundError);
    for (const place of defaultBlenderLocations("linux", {}, HOME)) expect(caught?.message).toContain(place);
    expect(caught?.message).toContain(BLENDER_DOWNLOAD_URL);
    expect(caught?.message).toContain(`Blender ${BLENDER_VERSION}`);
    expect(caught?.tried).toEqual(defaultBlenderLocations("linux", {}, HOME));
  });

  it("says a bare name is not on PATH", () => {
    expect(() => resolveBlender({ env: { BLENDER: "blender-nowhere", PATH: "/bin" }, platform: "linux", home: HOME, exists: () => false })).toThrow(
      /blender-nowhere, which is not on PATH/,
    );
  });
});
