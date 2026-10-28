import { readFileSync, realpathSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { containerShortfalls, containerText, probeContainer } from "../isolation.js";
import { judgeAsset } from "./asset.js";
import { jobsFor } from "./cpus.js";
import { layoutFrom } from "./inputs.js";
import { judgePatch } from "./patch.js";
import { probe } from "./probe.js";
import { emit, EntryError, EXIT, result, RESULT_PREFIX, type EntryResult } from "./result.js";

export const ENTRY_USAGE = `usage: blendworks-judge asset [--spec <file>] [--artifact <file or folder>]
       blendworks-judge patch [--artifact <file or folder>]
       blendworks-judge probe [--try <path>]...

Runs inside the judge image as Solive's --run command. asset judges the delivered asset against
the asset spec (the first \`\`\`json block of the job spec) with blendworks judge; patch applies the
delivered patch to the image's commit and runs npm run check. Both read only the input folder
(/judge: SPEC_PATH and ARTIFACT_PATH from Solive), write only the work folder, refuse to run outside
a sealed container, print one ${RESULT_PREFIX.trim()} JSON line and exit 0 on pass, 1 on fail and
75 when nothing was judged, which means try again later, never rejected. probe prints what the
container can reach.`;

function commitOf(env: NodeJS.ProcessEnv): string | null {
  if (env["BLENDWORKS_COMMIT"]) return env["BLENDWORKS_COMMIT"];
  try {
    return readFileSync(join(env["BLENDWORKS_ENTRY"] ?? "/opt/blendworks-entry", "commit"), "utf8").trim() || null;
  } catch {
    return null;
  }
}

export async function main(argv: string[], env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const [kind, ...rest] = argv;
  if (kind !== "asset" && kind !== "patch" && kind !== "probe") {
    console.error(ENTRY_USAGE);
    return EXIT.usage;
  }
  let values;
  try {
    ({ values } = parseArgs({ args: rest, strict: true, options: { spec: { type: "string" }, artifact: { type: "string" }, try: { type: "string", multiple: true } } }));
  } catch (error) {
    console.error(`${(error as Error).message}\n\n${ENTRY_USAGE}`);
    return EXIT.usage;
  }
  const layout = layoutFrom(env);
  const resultFile = join(layout.scratch, `${kind}-result.json`);
  const commit = commitOf(env);
  if (kind === "probe") return emit(await probe(layout, values.try ?? [], commit), resultFile);
  const container = probeContainer();
  const shortfalls = container === null ? ["not in a container"] : containerShortfalls(container);
  if (shortfalls.length > 0) return emit(result(kind, "error", `the judge image refuses to run outside a sealed container: ${shortfalls.join("; ")}`, { commit }), resultFile);
  const isolation = containerText(container!);
  let record: EntryResult;
  try {
    record =
      kind === "asset"
        ? judgeAsset({ layout, spec: values.spec ?? env["SPEC_PATH"], artifact: values.artifact ?? env["ARTIFACT_PATH"], commit, isolation, env })
        : await judgePatch({ layout, artifact: values.artifact ?? env["ARTIFACT_PATH"], commit, isolation, env, jobs: jobsFor(env) });
  } catch (error) {
    record =
      error instanceof EntryError
        ? result(kind, error.verdict, error.message, { commit, isolation })
        : result(kind, "fail", `the entry point failed on this delivery: ${error instanceof Error ? error.message : String(error)}`, { commit, isolation });
  }
  return emit(record, resultFile);
}

function invokedDirectly(): boolean {
  const entry = process.argv[1];
  if (entry === undefined) return false;
  try {
    return realpathSync(entry) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (invokedDirectly()) {
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (error: unknown) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = EXIT.fail;
    },
  );
}
