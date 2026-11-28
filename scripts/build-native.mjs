import { buildNativeMain } from "./lib/native-build.js";

process.exitCode = buildNativeMain();
