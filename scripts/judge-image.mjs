import { judgeImageMain } from "./lib/judge-image.js";

process.exitCode = await judgeImageMain(process.argv.slice(2));
