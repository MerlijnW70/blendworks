import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { autocorrelationPeak, highPass, luminance, type Grey } from "../../src/judge/natural-repetition.js";
import type { NaturalClass } from "../../src/judge/natural-spec.js";
import { decodePng } from "../../src/judge/visual/png.js";
import type { CalibrationInput } from "./natural-calibration-run.js";
import { repoRoot } from "./paths.js";
import { runBlender } from "./run.js";

export const TEXTURE_SCRIPT = join(repoRoot, "scripts", "lib", "texture-luminance.py");

export type TextureRepetition = { id: string; class: NaturalClass; image: string; size: [number, number]; untiled: number | null; tiled: number | null };

export function tiledTwice(grey: Grey): Grey {
  const width = grey.width * 2;
  const height = grey.height * 2;
  const values = new Float64Array(width * height);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) values[y * width + x] = grey.values[(y % grey.height) * grey.width + (x % grey.width)]!;
  return { width, height, values };
}

export function textureRepetitionOf(grey: Grey): { untiled: number | null; tiled: number | null } {
  return { untiled: autocorrelationPeak(highPass(grey)).peak, tiled: autocorrelationPeak(highPass(tiledTwice(grey))).peak };
}

type Written = { image: string; file: string | null; size: [number, number] | null; skipped?: string };

export async function textureRepetition(inputs: readonly CalibrationInput[], blender: string, root: string, workDir: string, log: (line: string) => void): Promise<TextureRepetition[]> {
  const found: TextureRepetition[] = [];
  for (const input of inputs.filter((entry) => entry.kind === "scan")) {
    const out = join(workDir, "textures", input.id);
    mkdirSync(out, { recursive: true });
    const result = await runBlender(blender, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", TEXTURE_SCRIPT, "--", input.path, out], { root, timeoutMs: 300_000, label: `textures/${input.id}` });
    if (result.code !== 0 || !existsSync(join(out, "textures.json"))) throw new Error(`reading the textures of ${input.id} failed\n${result.stderr.slice(-2000)}`);
    for (const written of JSON.parse(readFileSync(join(out, "textures.json"), "utf8")) as Written[]) {
      if (written.file === null || written.size === null) {
        log(`texture ${input.id} ${written.image}: skipped, ${written.skipped ?? "no file"}`);
        continue;
      }
      const peaks = textureRepetitionOf(luminance(decodePng(readFileSync(join(out, written.file)))));
      found.push({ id: input.id, class: input.classes[0]!, image: written.image, size: written.size, ...peaks });
      log(`texture ${input.id} ${written.image}: untiled ${peaks.untiled ?? "n/a"}, tiled 2 x 2 ${peaks.tiled ?? "n/a"}`);
    }
  }
  return found;
}
