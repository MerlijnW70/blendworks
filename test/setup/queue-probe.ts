import { setTimeout as sleep } from "node:timers/promises";
import { runUnderSlot } from "../../scripts/lib/run.js";

const [root = "", jobs = "1", log = "", label = "probe", holdMs = "300", count = "1", delayMs = "0"] = process.argv.slice(2);

const fakeBlender = `
const fs = require("node:fs");
const [log, label, hold] = process.argv.slice(1);
fs.appendFileSync(log, "start " + label + " " + Date.now() + "\\n");
setTimeout(() => fs.appendFileSync(log, "end " + label + " " + Date.now() + "\\n"), Number(hold));
`;

await sleep(Number(delayMs));
for (let run = 1; run <= Number(count); run += 1) {
  const result = await runUnderSlot(process.execPath, ["-e", fakeBlender, log, `${label}${run}`, holdMs], { root, jobs: Number(jobs), pollMs: 10 });
  if (result.code !== 0) process.exitCode = 1;
}
