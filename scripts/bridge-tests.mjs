import { bridgeMain } from "./lib/bridge-runner.js";

process.exitCode = await bridgeMain(process.argv.slice(2));
