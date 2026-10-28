import { readdirSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { activeSlots, queueDirectory, slotsDirectory } from "../../scripts/lib/slots.js";
import { NestedSlotError, slotsHeld, takeSlot, untilProcessExits, whileProcessRunsSync } from "../setup/slot.js";
import { scratch } from "./probes.js";

const saved = { cache: process.env["BLENDWORKS_CACHE"], jobs: process.env["BLENDWORKS_JOBS"] };
let root = "";

beforeEach(() => {
  root = scratch("nested-slots");
  process.env["BLENDWORKS_CACHE"] = root;
  process.env["BLENDWORKS_JOBS"] = "2";
});

afterEach(() => {
  for (const [name, value] of [["BLENDWORKS_CACHE", saved.cache], ["BLENDWORKS_JOBS", saved.jobs]] as const) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
});

function tickets(): string[] {
  try {
    return readdirSync(queueDirectory(slotsDirectory(root)));
  } catch {
    return [];
  }
}

describe("a test that holds a Blender slot", { timeout: 20_000 }, () => {
  it("is refused another slot at once while a session it started holds one, before it joins the queue", async () => {
    let exit = () => {};
    const exited = new Promise<void>((done) => (exit = done));
    await untilProcessExits(async () => "session", () => exited);
    expect(slotsHeld()).toEqual({ bounded: 0, lasting: 1 });
    await expect(takeSlot()).rejects.toBeInstanceOf(NestedSlotError);
    await expect(untilProcessExits(async () => "second session", () => exited)).rejects.toBeInstanceOf(NestedSlotError);
    expect(() => whileProcessRunsSync(() => "blocking")).toThrow(NestedSlotError);
    expect(tickets()).toEqual([]);
    expect(activeSlots(root)).toHaveLength(1);
    exit();
    await exited;
    await new Promise((done) => setTimeout(done, 0));
    expect(slotsHeld()).toEqual({ bounded: 0, lasting: 0 });
    const next = await takeSlot();
    next.release();
    expect(activeSlots(root)).toEqual([]);
  });

  it("is refused a blocking wait for a slot while one of its processes holds one", async () => {
    const running = await takeSlot();
    expect(() => whileProcessRunsSync(() => "blocking")).toThrow(NestedSlotError);
    running.release();
    expect(whileProcessRunsSync(() => slotsHeld())).toEqual({ bounded: 1, lasting: 0 });
    expect(slotsHeld()).toEqual({ bounded: 0, lasting: 0 });
  });

  it("still lets processes that end by themselves wait side by side", async () => {
    const [first, second] = await Promise.all([takeSlot(), takeSlot()]);
    expect(slotsHeld()).toEqual({ bounded: 2, lasting: 0 });
    first.release();
    second.release();
    expect(activeSlots(root)).toEqual([]);
  });
});
