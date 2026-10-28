import { existsSync, readFileSync } from "node:fs";
import { runUnderSlot } from "../../scripts/lib/run.js";
import { waitFor } from "./wait-for.js";

const [root = "", jobs = "1", log = "", label = "probe", hold = "300", count = "1", after = ""] = process.argv.slice(2);

const fakeBlender = `
const fs = require("node:fs");
const path = require("node:path");
const [log, label, hold, queue] = process.argv.slice(1);
fs.appendFileSync(log, "start " + label + " " + Date.now() + "\\n");
const finish = () => fs.appendFileSync(log, "end " + label + " " + Date.now() + "\\n");
if (hold === "ticket") {
  const poll = setInterval(() => {
    if (fs.existsSync(queue) && fs.readdirSync(queue).some((name) => name.endsWith(".ticket"))) {
      clearInterval(poll);
      finish();
    }
  }, 5);
} else setTimeout(finish, Number(hold));
`;

function started(label: string): boolean {
  return existsSync(log) && readFileSync(log, "utf8").split("\n").some((line) => line.startsWith(`start ${label}1 `));
}

if (after !== "") await waitFor(() => started(after), { description: `${after} to hold the slot` });
for (let run = 1; run <= Number(count); run += 1) {
  const holdFor = run === 1 ? hold : "30";
  const queue = `${root}/slots/queue`;
  const result = await runUnderSlot(process.execPath, ["-e", fakeBlender, log, `${label}${run}`, holdFor, queue], { root, jobs: Number(jobs), pollMs: 10 });
  if (result.code !== 0) process.exitCode = 1;
}
