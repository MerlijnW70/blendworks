import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { judge } from "../src/judge/run.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; name: string | null; mesh: { vertices: number } | null };

describe("the rocks example", workBudget(400_000), () => {
  it("builds fresh and worn rocks with commands only, renders them and scores the worn ones with the natural rules", async () => {
    const out = freshDir("rocks-example");
    const env = { ...process.env, BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_BAKE_SIZE: "128", BLENDWORKS_FRAGMENTS: "7", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/rocks.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    for (const command of ["fracture", "chip", "abrade", "noise_displace"]) expect(log.some((entry) => entry.cmd === command), command).toBe(true);
    expect(log.filter((entry) => entry.cmd === "abrade")).toHaveLength(3);
    for (const name of ["overview", "boulder", "stones"]) expect(statSync(join(out, `${name}.png`)).size, name).toBeGreaterThan(1_000);
    expect(existsSync(join(out, "rocks.blend"))).toBe(true);
    const measured: Record<string, boolean> = {};
    for (const stone of ["stone_a", "stone_b", "stone_c"]) {
      const report = await judge({ specPath: join(out, "rock.spec.json"), assetPath: join(out, `${stone}.glb`), outDir: join(out, `judge-${stone}`), preview: true });
      const rules = report.rules.filter((rule) => rule.rule.startsWith("natural."));
      expect(rules.map((rule) => rule.rule).sort()).toEqual(["natural.albedoVariation", "natural.solidity", "natural.surfaceRoughness"]);
      measured[stone] = rules.every((rule) => rule.pass);
    }
    expect(measured, JSON.stringify(measured)).toEqual({ stone_a: true, stone_b: true, stone_c: true });
  });
});
