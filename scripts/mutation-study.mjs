import { studyMain } from "./lib/mutation-study-main.js";

process.exitCode = await studyMain(process.argv.slice(2));
