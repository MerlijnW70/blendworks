import { runUnderSlot } from "../../scripts/lib/run.js";

const [root = "", jobs = "1", log = "", label = "probe", holdMs = "300"] = process.argv.slice(2);

const fakeBlender = `
const fs = require("node:fs");
const [log, label, hold] = process.argv.slice(1);
fs.appendFileSync(log, "start " + label + " " + Date.now() + "\\n");
setTimeout(() => {
  fs.appendFileSync(log, "end " + label + " " + Date.now() + "\\n");
}, Number(hold));
`;

const result = await runUnderSlot(process.execPath, ["-e", fakeBlender, log, label, holdMs], { root, jobs: Number(jobs) });
process.exitCode = result.code ?? 1;
