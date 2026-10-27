import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { main } from "../../src/judge/cli.js";
import { CLOSEUP_NAMES, CLOSEUP_SHEET, closeups } from "../../src/judge/closeups.js";
import { freshDir, makeFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtures("closeups"));
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function pngSize(path: string): [number, number] {
  const data = readFileSync(path);
  expect(data.subarray(1, 4).toString("latin1")).toBe("PNG");
  return [data.readUInt32BE(16), data.readUInt32BE(20)];
}

describe("close-ups", workBudget(180_000), () => {
  it("renders the hero view and two 2 x 2 grids, 9 non-empty PNGs, plus a labelled sheet", async () => {
    const outDir = freshDir("closeups", "crate");
    const result = await closeups({ assetPath: join(assets, "crate.glb"), outDir, resolution: 160, samples: 4 });
    expect(CLOSEUP_NAMES).toEqual([
      "hero",
      "front-right-top-left",
      "front-right-top-right",
      "front-right-bottom-left",
      "front-right-bottom-right",
      "back-left-top-left",
      "back-left-top-right",
      "back-left-bottom-left",
      "back-left-bottom-right",
    ]);
    expect(result.images.map((image) => image.name)).toEqual(CLOSEUP_NAMES);
    for (const image of result.images) {
      expect(statSync(image.path).size, image.name).toBeGreaterThan(500);
      expect(pngSize(image.path), image.name).toEqual([160, 160]);
    }
    expect(result.sheet).toBe(join(outDir, CLOSEUP_SHEET));
    const [width, height] = pngSize(result.sheet);
    expect(width).toBeGreaterThan(3 * 160);
    expect(height).toBeGreaterThan(160);
    expect(readdirSync(outDir).filter((name) => name.endsWith(".png")).sort()).toEqual([...CLOSEUP_NAMES.map((name) => `${name}.png`), CLOSEUP_SHEET].sort());
    expect(result.timings.total).toBeGreaterThan(0);
    expect(result.timings.render).toBeGreaterThan(0);
  });

  it("renders on the CPU when asked, under the original limits", async () => {
    const result = await closeups({ assetPath: join(assets, "crate.glb"), outDir: freshDir("closeups", "cpu"), resolution: 64, samples: 2, device: "cpu" });
    expect(result.device).toMatchObject({ kind: "cpu", fallback: null });
    expect(result.timings.device).toBeNull();
    expect(result.images).toHaveLength(9);
  });

  it("prints the device and its total time from the command line", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const outDir = freshDir("closeups", "command");
    expect(await main(["closeups", join(assets, "crate.glb"), "--out", outDir, "--res", "64", "--samples", "2"])).toBe(0);
    const printed = log.mock.calls.map((call) => String(call[0])).join("\n");
    expect(printed).toContain("close-ups: 9 images in");
    expect(printed).toMatch(/\n {2}render: (gpu|cpu)/);
    expect(printed).toMatch(/total \d+\.\d\d s/);
  });

  it("documents its defaults and refuses bad options", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(await main(["closeups", "--help"])).toBe(0);
    expect(String(log.mock.calls[0]?.[0])).toContain("Defaults: --res 1200 px, --samples 16 with denoising");
    expect(await main(["closeups", "a.glb"])).toBe(2);
    expect(await main(["closeups", "a.glb", "--out", "x", "--res", "0"])).toBe(2);
    expect(await main(["closeups", "a.glb", "--out", "x", "--samples", "many"])).toBe(2);
    expect(await main(["closeups", "a.glb", "--out", "x", "--res", "5000"])).toBe(2);
    expect(error).toHaveBeenCalled();
    expect(await main(["closeups", join(assets, "missing.glb"), "--out", freshDir("closeups", "missing")])).toBe(1);
  });
});
