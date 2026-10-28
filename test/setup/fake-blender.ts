export const FAKE_BLENDER = `
const fs = require("node:fs");
const [log, label, hold] = process.argv.slice(1);
const now = () => Number(process.hrtime.bigint() / 1000000n);
const started = now();
fs.appendFileSync(log, "start " + label + " " + started + "\\n");
const finish = () => {
  const left = started + Number(hold) - now();
  if (left > 0) setTimeout(finish, left);
  else fs.appendFileSync(log, "end " + label + " " + now() + "\\n");
};
finish();
`;
