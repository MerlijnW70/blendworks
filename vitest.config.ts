import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    maxWorkers: 4,
    testTimeout: 60_000,
    globalSetup: ["test/setup/global.ts"],
    setupFiles: ["test/setup/version-once.ts"],
  },
});
