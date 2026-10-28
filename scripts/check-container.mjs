import { containerCheckMain } from "./lib/container-check.js";

process.exitCode = await containerCheckMain(process.argv.slice(2));
