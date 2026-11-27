import { describe, expect, it } from "vitest";
import { describeRecovery } from "../src/mcp/recovery.js";

const SNAPSHOT = { generation: 3, saved_at: "2026-11-27T12:00:00Z", reason: "when idle", bytes: 1000, objects: 4 };

describe("the recovery message", () => {
  it("names the snapshot and the journaled requests replayed after it", () => {
    const result = { restored: true, path: ".blendworks/autosave-3.blend", saved_at: SNAPSHOT.saved_at, reason: "snapshot when idle, then 12 journaled requests replayed", objects: 7, snapshot: SNAPSHOT, replayed: { requests: 12, seconds: 3.5 } };
    expect(describeRecovery(result)).toBe(
      "Reloaded the snapshot .blendworks/autosave-3.blend saved at 2026-11-27T12:00:00Z (when idle) and replayed 12 journaled requests after it; the scene has 7 objects. Check with blender_scene_info before continuing.",
    );
  });

  it("lists the requests that were not replayed and why, and images it could not restore", () => {
    const result = {
      restored: true,
      path: ".blendworks/autosave-3.blend",
      saved_at: SNAPSHOT.saved_at,
      objects: 1,
      snapshot: SNAPSHOT,
      replayed: { requests: 1, seconds: 0.1 },
      not_replayed: [{ seq: 2, cmd: "image_load" }, { seq: 3, cmd: "add_primitive" }],
      not_replayed_reason: "its input red.png changed since it was journaled",
      unsaved_images: ["baked"],
    };
    expect(describeRecovery(result)).toBe(
      "Reloaded the snapshot .blendworks/autosave-3.blend saved at 2026-11-27T12:00:00Z (when idle) and replayed 1 journaled request after it; the scene has 1 object. " +
        "Not replayed: requests 2 image_load, 3 add_primitive because its input red.png changed since it was journaled; redo them if they are still needed. " +
        "These images had unsaved pixels that could not be restored: baked. Check with blender_scene_info before continuing.",
    );
  });

  it("keeps the earlier wording for an autosave without a journal", () => {
    expect(describeRecovery({ restored: true, path: ".blendworks/autosave.blend", saved_at: null, reason: "an autosave from an earlier version", objects: 1 })).toBe(
      "Reloaded .blendworks/autosave.blend (an autosave from an earlier version); the scene has 1 object. Changes after that autosave are lost; check with blender_scene_info before continuing.",
    );
  });
});
