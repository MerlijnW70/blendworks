import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Shot = {
  weather: { storm: number; cover: number; rain: { rate: number; veil: boolean }; lightning: { bolt: string } | null; exposure: { scene: number }; lamp: { strength: number } };
  clouds: { form: string; layers: string[] } | null;
};
type Summary = { shots: Record<string, Shot>; commands: { cmd: string }[] };

describe("the weather scene example", workBudget(400_000), () => {
  it("builds the outdoor scene by commands only and renders it under clear sky and thunderstorm", () => {
    const out = freshDir("weather-scene-example");
    const env = {
      ...process.env,
      BLENDWORKS_SHOT_WIDTH: "64",
      BLENDWORKS_SHOT_HEIGHT: "36",
      BLENDWORKS_SHOT_SAMPLES: "2",
      BLENDWORKS_SHOT_SECONDS: "60",
      BLENDWORKS_TREE_DETAIL: "0.05",
      BLENDWORKS_COVER_BUDGET: "3000",
      BLENDWORKS_CLOUD_FORM: "sheet",
      BLENDWORKS_DEVICE: "cpu",
    };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/weather_scene.py", "--", out, "clear,thunderstorm", "noon"], { env, stdio: "pipe" });
    const summary = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Summary;
    const used = new Set(summary.commands.map((entry) => entry.cmd));
    for (const command of ["heightfield", "chip", "abrade", "instances", "grow_tree", "tree_mesh", "tree_leaves", "ground_cover", "weather", "render_final"]) expect(used.has(command), command).toBe(true);
    expect(used.has("set_world_hdri")).toBe(false);
    for (const command of ["distant_land", "distant_forest", "valley_mist"]) expect(used.has(command), command).toBe(false);
    const clear = summary.shots["clear-noon"]!;
    const storm = summary.shots["thunderstorm-noon"]!;
    expect(clear.weather.storm).toBe(0);
    expect(clear.weather.cover).toBe(0);
    expect(clear.clouds).toBeNull();
    expect(storm.weather.storm).toBe(1);
    expect(storm.weather.cover).toBeGreaterThan(0.9);
    expect(storm.weather.rain.veil).toBe(true);
    expect(storm.weather.lightning?.bolt).toBe("Lightning");
    expect(storm.clouds?.layers).toContain("nimbostratus");
    expect(storm.clouds?.layers).not.toContain("cumulonimbus");
    expect(storm.weather.exposure.scene).toBeGreaterThan(clear.weather.exposure.scene);
    for (const name of ["clear-noon", "thunderstorm-noon"]) expect(statSync(join(out, `${name}.png`)).size, name).toBeGreaterThan(500);
    expect(existsSync(join(out, "weather-scene.blend"))).toBe(true);
  });
});
