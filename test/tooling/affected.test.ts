import { describe, expect, it } from "vitest";
import { type Change, type Repo, parseHunks, selectAffected, workingRepo } from "../../scripts/lib/affected.js";
import { buildGraph, type Source } from "../../scripts/lib/dep-graph.js";

const PACKAGE = "bridge/blendworks_bridge";

const FILES: Record<string, string> = {
  "package.json": "{}",
  "src/geometry.ts": 'export function area(a: number): number {\n  return a * a;\n}\n',
  "src/report.ts": 'import { area } from "./geometry.js";\n\nexport function report(a: number): string {\n  return String(area(a));\n}\n',
  "src/clock.ts": "export function now(): number {\n  return 1;\n}\n",
  "test/report.test.ts": 'import { report } from "../src/report.js";\nreport(2);\n',
  "test/clock.test.ts": 'import { now } from "../src/clock.js";\nnow();\n',
  "test/scene.test.ts": 'import { useBlenderSlot } from "./setup/slot.js";\nuseBlenderSlot();\nconst tool = "blender_add_light";\n',
  "test/setup/slot.ts": "export function useBlenderSlot(): void {}\n",
  "scripts/lib/pipeline.ts": "export const steps = 1;\n",
  [`${PACKAGE}/__init__.py`]: "from .handler import Handler\n",
  [`${PACKAGE}/handler.py`]: "from . import commands\n\n\nclass Handler:\n    def __init__(self):\n        commands.load()\n",
  [`${PACKAGE}/registry.py`]: "COMMANDS = {}\n\n\ndef command(name):\n    def register(run):\n        COMMANDS[name] = run\n        return run\n    return register\n",
  [`${PACKAGE}/commands/__init__.py`]: 'import importlib\n\nMODULES = (\n    "lights",\n    "sky",\n    "stage",\n)\n\n\ndef load():\n    for name in MODULES:\n        importlib.import_module(f"{__name__}.{name}")\n',
  [`${PACKAGE}/glow.py`]: "def strength(value):\n    return value * 2\n\n\ndef label(text):\n    return text.upper()\n",
  [`${PACKAGE}/commands/lights.py`]: 'from .. import glow\nfrom ..registry import command\n\nTITLE = glow.label("lights")\n\n\n@command("add_light")\ndef add_light(args):\n    return glow.strength(args["energy"])\n',
  [`${PACKAGE}/commands/sky.py`]: 'from ..registry import command\n\n\n@command("set_sky")\ndef set_sky(args):\n    return args\n',
  [`${PACKAGE}/commands/stage.py`]: 'from ..registry import COMMANDS, command\n\n\n@command("set_stage")\ndef set_stage(args):\n    return COMMANDS["add_light"](args)\n',
  "bridge/tests/test_stage.py": 'from harness import Handler\n\nHandler()\nbridge_call = ("set_stage", {})\n',
  "bridge/tests/harness.py": "import sys\n\nfrom blendworks_bridge import Handler\n",
  "bridge/tests/test_lights.py": 'from harness import Handler\n\nHandler()\nbridge_call = ("add_light", {"energy": 1})\n',
  "bridge/tests/test_sky.py": 'from harness import Handler\n\nHandler()\nbridge_call = ("set_sky", {})\n',
  "native/Cargo.toml": '[package]\nname = "kernels"\n\n[lib]\nname = "kernel_core"\n',
  "native/src/lib.rs": "pub fn flood() {}\n",
  [`${PACKAGE}/kernel_loader.py`]: 'def library():\n    return "kernel_core.dll"\n',
  "bridge/tests/test_kernels.py": "from blendworks_bridge import kernel_loader\n\nkernel_loader.library()\n",
  "docs/notes.md": "Notes nobody reads.\n",
  "assets/blob.bin": "",
};

function repo(files: Record<string, string> = FILES, base: Record<string, string> = files): Repo {
  const source: Source = { files: Object.keys(files).sort(), read: (file) => files[file] };
  return { source, graph: buildGraph(source), base: (file) => base[file] };
}

function modified(file: string, ...lines: number[]): Change {
  return { file, status: "M", baseLines: [], headLines: lines };
}

function selected(changes: Change[], target: Repo = repo()): string[] {
  const selection = selectAffected(changes, target);
  return [...selection.vitest, ...selection.bridge];
}

describe("the tests check:affected selects", () => {
  it("follows the TypeScript import graph from a source module to the tests that import it, directly or not", () => {
    const tests = selected([modified("src/geometry.ts", 2)]);
    expect(tests).toContain("test/report.test.ts");
    expect(tests).not.toContain("test/scene.test.ts");
  });

  it("selects the bridge tests that call a command whose module calls the changed function body, and not the others", () => {
    const tests = selected([modified(`${PACKAGE}/glow.py`, 2)]);
    expect(tests).toContain("bridge/tests/test_lights.py");
    expect(tests).not.toContain("bridge/tests/test_sky.py");
    expect(tests).toContain("test/scene.test.ts");
  });

  it("follows a bridge module that runs another command by name through the registry", () => {
    expect(selected([modified(`${PACKAGE}/glow.py`, 2)])).toContain("bridge/tests/test_stage.py");
  });

  it("maps a change to native code to the tests whose modules load its library, as a call-time change", () => {
    const tests = selected([modified("native/src/lib.rs", 1)]);
    expect(tests).toContain("bridge/tests/test_kernels.py");
    expect(tests).not.toContain("bridge/tests/test_sky.py");
  });

  it("treats a function that runs while modules load as loaded by every user of the handler", () => {
    const tests = selected([modified(`${PACKAGE}/glow.py`, 6)]);
    expect(tests).toEqual(expect.arrayContaining(["bridge/tests/test_lights.py", "bridge/tests/test_sky.py"]));
  });

  it("treats a module-level line of a command module as loaded by every user of the handler", () => {
    const tests = selected([modified(`${PACKAGE}/commands/lights.py`, 4)]);
    expect(tests).toEqual(expect.arrayContaining(["bridge/tests/test_lights.py", "bridge/tests/test_sky.py"]));
    expect(selected([modified(`${PACKAGE}/commands/lights.py`, 9)])).not.toContain("bridge/tests/test_sky.py");
  });

  it("always runs the unit tests that need no Blender and nothing else for a document no test reads", () => {
    const selection = selectAffected([modified("docs/notes.md", 1)], repo());
    expect(selection.everything).toBe(false);
    expect(selection.vitest).toEqual(["test/clock.test.ts", "test/report.test.ts"]);
  });

  it("selects everything for shared infrastructure, a deleted or renamed file, and a file the map cannot place", () => {
    for (const change of [modified("scripts/lib/pipeline.ts", 1), modified("bridge/tests/harness.py", 1), modified(`${PACKAGE}/handler.py`, 6), modified("package.json", 1), modified("assets/blob.bin", 1), { file: "src/clock.ts", status: "D" as const, baseLines: [], headLines: [] }]) {
      const selection = selectAffected([change], repo());
      expect(selection.everything, change.file).toBe(true);
      expect(selection.bridge.length, change.file).toBe(4);
      expect(selection.reasons.join("\n"), change.file).toContain("everything");
    }
  });

  it("reads the changed lines of each hunk on both sides of a diff", () => {
    expect(parseHunks("@@ -3,2 +3,0 @@\n@@ -10 +9,3 @@\n")).toEqual({ baseLines: [3, 4, 10], headLines: [9, 10, 11] });
  });

  it("maps a body change in a real bridge module to its tests and not to unrelated ones", () => {
    const real = workingRepo("HEAD");
    const file = `${PACKAGE}/stone_shape.py`;
    const text = real.source.read(file) ?? "";
    const line = text.split("\n").findIndex((row, index) => index > 0 && /^ {4}return /.test(row)) + 1;
    expect(line).toBeGreaterThan(1);
    const selection = selectAffected([{ file, status: "M", baseLines: [line], headLines: [line] }], { ...real, base: (name) => real.source.read(name) });
    expect(selection.everything).toBe(false);
    expect(selection.bridge).toContain("bridge/tests/test_shore_stones.py");
    expect(selection.bridge).not.toContain("bridge/tests/test_tree_mesh.py");
    expect(selection.reasons.join("\n")).toContain("what calls it");
  });
});
