import { judgeCommandMain } from "./lib/judge-command.js";

process.exitCode = judgeCommandMain(process.argv.slice(2));
