import { defineConfig } from "vitest/config";
import HeaviestFirstSequencer from "./test/setup/sequencer.js";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    maxWorkers: 4,
    testTimeout: 60_000,
    env: { BLENDWORKS_TEST_RENDER: "test", BLENDWORKS_DEVICE: "cpu" },
    globalSetup: ["test/setup/global.ts"],
    setupFiles: ["test/setup/version-once.ts", "test/setup/work.ts"],
    sequence: { sequencer: HeaviestFirstSequencer },
  },
});
