import { cleanMain } from "./lib/clean.js";

process.exitCode = cleanMain(process.argv.slice(2));
