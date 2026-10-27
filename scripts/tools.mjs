import { toolsMain } from "./lib/tools.js";

process.exitCode = await toolsMain(process.argv.slice(2));
