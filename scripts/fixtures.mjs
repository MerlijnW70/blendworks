import { ensureFixtures, MAIN_SET } from "./lib/fixtures.js";

const wanted = process.argv[2] ?? MAIN_SET;
const sets = await ensureFixtures();
const set = sets[wanted];
if (set === undefined) {
  console.error(`no fixture set named ${wanted}; the sets are ${Object.keys(sets).join(", ")}`);
  process.exit(1);
}
console.log(set.assets);
