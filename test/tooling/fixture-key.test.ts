import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { fixtureKey } from "../../scripts/lib/fixtures.js";
import { freshDir } from "../judge/helpers.js";

describe("the fixture cache key", () => {
  it("changes when a bridge module changes, and only then", () => {
    const base = freshDir("fixture-key");
    const bridge = join(base, "bridge", "blendworks_bridge", "commands");
    mkdirSync(bridge, { recursive: true });
    writeFileSync(join(base, "fixtures.py"), "print(1)\n");
    writeFileSync(join(bridge, "abrade.py"), "x = 1\n");
    const script = join(base, "fixtures.py");
    const before = fixtureKey(script, "5.2", base);
    expect(fixtureKey(script, "5.2", base)).toBe(before);
    writeFileSync(join(bridge, "abrade.py"), "x = 2\n");
    const edited = fixtureKey(script, "5.2", base);
    expect(edited).not.toBe(before);
    writeFileSync(join(base, "bridge", "blendworks_bridge", "notes.txt"), "ignored\n");
    expect(fixtureKey(script, "5.2", base)).toBe(edited);
    expect(fixtureKey(script, "5.3", base)).not.toBe(edited);
  });
});
