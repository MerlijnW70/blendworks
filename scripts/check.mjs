import { checkMain } from "./lib/checks.js";

process.exitCode = await checkMain();
