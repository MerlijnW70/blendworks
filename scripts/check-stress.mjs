import { stressMain } from "./lib/stress.js";

process.exitCode = await stressMain(process.argv.slice(2));
