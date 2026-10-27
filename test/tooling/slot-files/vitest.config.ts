import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/tooling/slot-files/*.spec.ts"],
    environment: "node",
    maxWorkers: 2,
    setupFiles: ["test/setup/version-once.ts", "test/setup/work.ts"],
  },
});
