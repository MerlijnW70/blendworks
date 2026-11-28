import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { mutatePython, mutateScript } from "../../scripts/lib/mutation.js";
import { runStudy, type Suite } from "../../scripts/lib/mutation-study.js";
import { useBlenderSlot } from "../setup/slot.js";
import { scratch } from "./probes.js";

useBlenderSlot();

const FILES: Record<string, string> = {
  "package.json": "{}\n",
  "src/maths.ts": "export function double(value: number): number {\n  return value * 2;\n}\n",
  "src/words.ts": "export function shout(text: string): string {\n  return text.toUpperCase();\n}\n",
  "test/maths.test.ts": 'import { double } from "../src/maths.ts";\nconst marker = "useBlenderSlot()";\nif (double(2) !== 4) throw new Error(marker);\n',
  "test/words.test.ts": 'import { shout } from "../src/words.ts";\nconst marker = "useBlenderSlot()";\nif (shout("a") !== "A") throw new Error(marker);\n',
  "bridge/package/package_counting.py": "def count(items):\n    return len(items)\n\n\nclass Tally:\n    def total(self, items):\n        return count(items)\n",
  "bridge/tests/test_counting.py": 'import os\nimport sys\n\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "package"))\n\nfrom package_counting import Tally\n\nassert Tally().total([1, 2]) == 2\n',
  "bridge/tests/test_alone.py": "assert sum([1, 2]) == 3\n",
};

let root = "";
let cache = "";

const suite: Suite = async (folder, only) => {
  const started = performance.now();
  const files = only ?? Object.keys(FILES).filter((file) => /^test\/.*\.test\.ts$|^bridge\/tests\/test_.*\.py$/.test(file));
  const failing: string[] = [];
  for (const file of files) {
    const run = file.endsWith(".py")
      ? spawnSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(folder, file)], { cwd: folder, encoding: "utf8" })
      : spawnSync(process.execPath, ["--experimental-strip-types", "--no-warnings", join(folder, file)], { cwd: folder, encoding: "utf8" });
    if (run.status !== 0) failing.push(file);
  }
  return { failing, files: files.length, fixtureBuildFailed: false, seconds: (performance.now() - started) / 1000 };
};

describe("the mutation study, small version", () => {
  beforeAll(() => {
    root = scratch("mutation-study");
    cache = join(root, ".cache");
    for (const [file, text] of Object.entries(FILES)) {
      mkdirSync(join(root, file, ".."), { recursive: true });
      writeFileSync(join(root, file), text);
    }
    execFileSync("git", ["init", "--quiet"], { cwd: root });
  });

  it("breaks every function of a module once, runs the whole suite, and finds every failing test in the selection", async () => {
    const lines: string[] = [];
    const study = await runStudy(root, ["src/maths.ts", "src/words.ts", "bridge/package/package_counting.py"], suite, { cache, log: (line) => lines.push(line) });
    expect(study.baseline).toEqual([]);
    expect(study.results.map((result) => [result.module, result.failing, result.missed])).toEqual([
      ["src/maths.ts", ["test/maths.test.ts"], []],
      ["src/words.ts", ["test/words.test.ts"], []],
      ["bridge/package/package_counting.py", ["bridge/tests/test_counting.py"], []],
    ]);
    for (const [file, text] of Object.entries(FILES)) expect(readFileSync(join(root, file), "utf8"), file).toBe(text);
  });

  it("reports a failing test outside the selection, so a selection that drops a dependency cannot pass", async () => {
    const study = await runStudy(root, ["bridge/package/package_counting.py"], suite, { cache, log: () => undefined, select: () => ({ selected: new Set(["bridge/tests/test_alone.py"]), everything: false }) });
    expect(study.results[0]?.missed).toEqual(["bridge/tests/test_counting.py"]);
  });

  it("finds the same failures when it breaks a group of modules at once and checks each outside failure with its module alone", async () => {
    const study = await runStudy(root, ["src/maths.ts", "bridge/package/package_counting.py"], suite, { cache, group: 2, log: () => undefined, select: (folder, file) => ({ selected: new Set(file.endsWith(".py") ? ["bridge/tests/test_counting.py"] : ["test/maths.test.ts"]), everything: false }) });
    expect(study.results.map((result) => [result.module, result.missed])).toEqual([
      ["src/maths.ts", []],
      ["bridge/package/package_counting.py", []],
    ]);
  });

  it("puts a guard at the top of every function body that raises once the module has loaded", () => {
    const python = mutatePython("a.py", FILES["bridge/package/package_counting.py"] as string);
    expect(python.functions).toBe(2);
    expect(python.text).toContain('if not getattr(globals().get("__spec__"), "_initializing", False): raise RuntimeError("planted bug in a.py")');
    const script = mutateScript("a.ts", FILES["src/maths.ts"] as string);
    expect(script.functions).toBe(1);
    expect(script.text.split("\n")[1]).toContain('__blendworksArmed?.has("a.ts")) throw new Error("planted bug in a.ts")');
    expect(script.text).toContain('__blendworksArmed ??= new Set()).add("a.ts");');
  });
});
