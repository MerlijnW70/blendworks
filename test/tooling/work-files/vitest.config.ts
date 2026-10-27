import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/tooling/work-files/*.spec.ts"],
    environment: "node",
    maxWorkers: 3,
    setupFiles: ["test/setup/version-once.ts", "test/setup/work.ts"],
  },
});
