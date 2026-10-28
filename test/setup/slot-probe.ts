import { runUnderSlot } from "../../scripts/lib/run.js";
import { FAKE_BLENDER } from "./fake-blender.js";

const [root = "", jobs = "1", log = "", label = "probe", holdMs = "300"] = process.argv.slice(2);


const result = await runUnderSlot(process.execPath, ["-e", FAKE_BLENDER, log, label, holdMs], { root, jobs: Number(jobs) });
process.exitCode = result.code ?? 1;
