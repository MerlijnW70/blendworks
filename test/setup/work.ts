import { afterAll, aroundEach, beforeAll } from "vitest";
import { observeWaits } from "../../scripts/lib/locks.js";
import { labelSlotsWith } from "../../scripts/lib/slots.js";
import { PROGRESS_VARIABLE } from "../../scripts/lib/progress.js";
import { currentStage, recordTiming } from "../../scripts/lib/timings.js";
import { defaultWorkBudgetMs } from "./slot.js";
import { currentWorkClock, slotTotals, testFile, underWorkClock } from "./work-clock.js";

delete process.env[PROGRESS_VARIABLE];

let file = "";
let fileStarted = 0;
let fileTotals = { waitMs: 0, acquisitions: 0 };

let pendingWaits = 0;
let waitBegan = 0;

observeWaits({
  waiting() {
    pendingWaits += 1;
    if (pendingWaits > 1) return;
    waitBegan = performance.now();
    if (file !== "") recordTiming({ kind: "wait", file, state: "begin" });
  },
  waited() {
    pendingWaits -= 1;
    if (pendingWaits === 0 && file !== "") recordTiming({ kind: "wait", file, state: "end", waitedMs: Math.round(performance.now() - waitBegan) });
  },
});

labelSlotsWith(() => currentWorkClock()?.label ?? (file === "" ? undefined : `"${file}"`));

beforeAll(() => {
  file = testFile();
  fileStarted = performance.now();
  fileTotals = slotTotals();
});

aroundEach(async (runTest, context) => {
  const label = `test "${context.task.fullName}"`;
  const budgetMs = context.task.meta.workBudgetMs ?? defaultWorkBudgetMs();
  if (budgetMs === undefined) {
    await runTest();
    return;
  }
  await underWorkClock(label, budgetMs, runTest);
});

afterAll(() => {
  const totals = slotTotals();
  recordTiming({ kind: "file", stage: currentStage(), file, wallMs: Math.round(performance.now() - fileStarted), waitMs: Math.round(totals.waitMs - fileTotals.waitMs), processes: totals.acquisitions - fileTotals.acquisitions, endedAt: Date.now() });
});
