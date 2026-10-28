import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { detectTools, MOUNT_SCRIPT, planSandbox, runSandboxed } from "../../src/judge/sandbox.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const MOUNTINFO_SCRIPT = join(dirname(MOUNT_SCRIPT), "mountinfo.awk");
const AWK = spawnSync("awk", ["BEGIN { exit 0 }"], { stdio: "ignore" }).status === 0;
const PROBE = resolve("test", "judge", "isolation_probe.py");
const TOP = "/sandbox/root/work/with space/delivery";

function mountinfo(lines: string[]): string {
  const folder = freshDir("sandbox-mounts", "mountinfo");
  const path = join(folder, "mountinfo");
  writeFileSync(path, `${lines.join("\n")}\n`);
  return path;
}

function awk(mode: "points" | "check", lines: string[], top = TOP): { code: number | null; output: string } {
  const run = spawnSync("awk", ["-f", MOUNTINFO_SCRIPT, mountinfo(lines)], { encoding: "utf8", env: { ...process.env, BLENDWORKS_TOP: top, BLENDWORKS_MODE: mode } });
  return { code: run.status, output: run.stdout.trim() };
}

const ENCODED = "/sandbox/root/work/with\\040space/delivery";

describe.runIf(AWK)("the sandbox reads its mounts from mountinfo", () => {
  it("decodes octal escapes, so a path with a space is found and remounted with the flags it has", () => {
    const found = awk("points", [`41 30 8:16 /x ${ENCODED} rw,nosuid,nodev,relatime shared:1 - ext4 /dev/sdb rw`]);
    expect(found).toEqual({ code: 0, output: `remount,bind,ro,nosuid,nodev,relatime\t${TOP}` });
    expect(awk("points", [`41 30 8:16 /x /a\\011tab\\012line\\134slash rw - ext4 /dev/sdb rw`], "/a\ttab\nline\\slash").output).toBe("remount,bind,ro\t/a\ttab\nline\\slash");
  });

  it("fails closed when a mount under a read-only path is still writable, or the path is not mounted at all", () => {
    expect(awk("check", [`41 30 8:16 /x ${ENCODED} ro,relatime - ext4 /dev/sdb rw`]).code).toBe(0);
    const writable = awk("check", [`41 30 8:16 /x ${ENCODED} ro,relatime - ext4 /dev/sdb rw`, `42 41 0:50 / ${ENCODED}/inner rw,relatime - tmpfs tmpfs rw`]);
    expect(writable).toEqual({ code: 1, output: `writable: ${TOP}/inner` });
    expect(awk("check", [`41 30 8:16 /x ${ENCODED}-other rw - ext4 /dev/sdb rw`])).toEqual({ code: 1, output: `not mounted: ${TOP}` });
    expect(awk("check", [`41 30 8:16 /x /sandbox/root/work/with space/delivery rw - ext4 /dev/sdb rw`]).code).toBe(1);
  });
});

describe.runIf(!AWK)("the sandbox's mountinfo reader", () => {
  it.skip("needs awk on the PATH", () => undefined);
});

describe("the read-only mounts on this machine", workBudget(120_000), () => {
  const tools = detectTools();

  it.runIf(tools.platform === "linux" && tools.mountNamespace === true)("keeps a delivery folder whose path has a space read-only inside the sandbox", async () => {
    const root = freshDir("sandbox-mounts", "with space");
    const work = join(root, "work");
    const delivery = join(work, "the delivery");
    const out = join(work, "out");
    for (const folder of [delivery, out]) mkdirSync(folder, { recursive: true });
    writeFileSync(join(delivery, "asset.glb"), "delivered");
    const result = join(out, "probe.json");
    rmSync(result, { force: true });
    const view = { workDir: work, writable: [out], readOnly: [SCRIPTS_DIR, dirname(PROBE), delivery] };
    const plan = planSandbox(blenderPath(), PROBE, [result, join(delivery, "asset.glb"), "--writes", join(delivery, "planted.txt"), join(out, "written.txt")], { timeoutMs: 60_000, memoryBytes: 2048 * 1024 * 1024 }, tools, "cpu", view);
    const run = await runSandboxed(plan, work);
    expect(existsSync(result), run.output.slice(-800)).toBe(true);
    const probe = JSON.parse(readFileSync(result, "utf8")) as { read: Record<string, string>; write: Record<string, string> };
    expect(probe.read[join(delivery, "asset.glb")]).toBe("read");
    expect(probe.write[join(delivery, "planted.txt")]).toMatch(/^refused/);
    expect(probe.write[join(out, "written.txt")]).toBe("written");
    expect(existsSync(join(delivery, "planted.txt"))).toBe(false);
  });
});
