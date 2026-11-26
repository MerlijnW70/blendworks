import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const SPECIES = ["oak", "birch", "pine", "willow", "maple", "olive"];

type Stat = { trees: number; mean: number; std: number };
type Calibration = { summary: { fill: Stat; foliage_fill: Stat }; trees: { asset: string; license: string; url: string; fill: number; foliage_fill: number }[] };

function fillBand(name = "FILL_BAND"): [number, number] {
  const source = readFileSync("bridge/blendworks_bridge/tree_crown.py", "utf8");
  const found = new RegExp(`^${name} = \\(([\\d.]+), ([\\d.]+)\\)$`, "m").exec(source);
  if (found === null) throw new Error(`tree_crown.py has no ${name} = (low, high) line`);
  return [Number(found[1]), Number(found[2])];
}

describe("the tree realism references", () => {
  it("keep the crown fill band at the mean plus or minus two deviations of the CC0 scans", () => {
    const calibration = JSON.parse(readFileSync("docs/research/tree-realism/crown-fill.json", "utf8")) as Calibration;
    expect(calibration.trees.length).toBe(calibration.summary.fill.trees);
    expect(calibration.trees.length).toBeGreaterThanOrEqual(10);
    for (const tree of calibration.trees) {
      expect(tree.license, tree.asset).toBe("CC0");
      expect(tree.url, tree.asset).toMatch(/^https:\/\/polyhaven\.com\/a\//);
    }
    for (const [key, band] of [["fill", fillBand()], ["foliage_fill", fillBand("FOLIAGE_BAND")]] as const) {
      const values = calibration.trees.map((tree) => tree[key]);
      const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
      const deviation = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length);
      expect(Math.abs(mean - calibration.summary[key].mean), key).toBeLessThan(1e-3);
      expect(Math.abs(band[0] - (mean - 2 * deviation)), key).toBeLessThan(0.005);
      expect(Math.abs(band[1] - (mean + 2 * deviation)), key).toBeLessThan(0.005);
    }
  });

  it("document every species preset with a CC0 reference photo", () => {
    const notes = readFileSync("docs/research/tree-realism.md", "utf8");
    const design = readFileSync("docs/DESIGN.md", "utf8");
    for (const species of SPECIES) {
      const row = notes.split("\n").find((line) => line.startsWith(`| ${species}, `));
      expect(row, species).toBeDefined();
      expect(row, species).toMatch(/https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
      expect(design, species).toContain(`| \`${species}\` (`);
    }
    expect(notes).toContain("CC0");
  });
});
