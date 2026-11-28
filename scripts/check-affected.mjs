import { affectedMain } from "./lib/checks.js";

process.exitCode = await affectedMain();
