import { afterAll, aroundEach, beforeAll } from "vitest";
import { labelSlotsWith } from "../../scripts/lib/slots.js";
import { currentStage, recordTiming } from "../../scripts/lib/timings.js";
import { defaultWorkBudgetMs } from "./slot.js";
import { currentWorkClock, slotTotals, testFile, underWorkClock } from "./work-clock.js";

let file = "";
let fileStarted = 0;
let fileTotals = { waitMs: 0, acquisitions: 0 };

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
