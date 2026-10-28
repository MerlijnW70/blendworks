import type { Reporter, TestModule } from "vitest/node";
import { announceFile } from "../../scripts/lib/progress.js";

export default class ProgressReporter implements Reporter {
  onTestModuleStart(module: TestModule): void {
    announceFile({ event: "start", file: module.relativeModuleId, limited: true });
  }

  onTestModuleEnd(module: TestModule): void {
    announceFile({ event: "end", file: module.relativeModuleId, passed: module.state() !== "failed", seconds: (module.diagnostic().duration ?? 0) / 1000 });
  }
}
