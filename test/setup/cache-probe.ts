import { appendFileSync } from "node:fs";
import { ensureEntry } from "../../scripts/lib/entry-cache.js";

const [root = "", key = "key", counter = ""] = process.argv.slice(2);

const entry = await ensureEntry({
  root,
  name: "probe",
  key,
  generate: async () => {
    appendFileSync(counter, "generated\n");
    await new Promise((resolve) => setTimeout(resolve, 400));
  },
});
console.log(JSON.stringify({ generated: entry.generated }));
