import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { withSlot } from "../../scripts/lib/slots.js";
import { CORE_FILL } from "../../src/mcp/routing/core.generated.js";
import { CORE_HYSTERESIS, CORE_LIMITS, CORE_PINNED, CORE_WRITE_COMMAND, rankCore, updateFill } from "../../src/mcp/routing/core.js";
import { toolSizes } from "../../src/mcp/routing/disclosure.js";
import { derivedCoreScores } from "./core-data.js";
import { productRoutes } from "./modes.js";
import { startBenchServer } from "./server.js";

export const CORE_FILE = fileURLToPath(new URL("../../src/mcp/routing/core.generated.ts", import.meta.url));

export function coreFile(fill: string[]): string {
  return `export const CORE_FILL: string[] = ${JSON.stringify(fill).replace(/","/g, '", "')};\n`;
}

export function sameMembers(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((name) => right.includes(name));
}

export function coreReport(scores: Map<string, number>, sizes: Map<string, number>, fill: string[], shown = 8): string[] {
  const score = (name: string) => (scores.get(name) ?? 0).toFixed(4);
  const weakest = Math.min(...fill.map((name) => scores.get(name) ?? 0));
  const lines = [`pinned: ${CORE_PINNED.map((name) => `${name} ${score(name)}`).join(", ")}`, `fill:   ${fill.map((name) => `${name} ${score(name)} (${sizes.get(name)} bytes)`).join(", ")}`];
  const outside = rankCore(scores).filter((name) => sizes.has(name) && !CORE_PINNED.includes(name) && !fill.includes(name)).slice(0, shown);
  const size = (name: string) => sizes.get(name) ?? 0;
  const room = CORE_LIMITS.budgetBytes - CORE_PINNED.reduce((sum, name) => sum + size(name), 0);
  const used = fill.reduce((sum, name) => sum + size(name), 0);
  for (const name of outside) {
    const gap = (scores.get(name) ?? 0) - weakest;
    const fits = fill.some((member) => used - size(member) + size(name) <= room);
    lines.push(`  out ${name} ${score(name)} (${size(name)} bytes), ${gap >= 0 ? "+" : ""}${gap.toFixed(4)} against the weakest fill member; ${fits ? `hysteresis ${CORE_HYSTERESIS}` : `too big for the ${room} bytes the pinned tools leave`}`);
  }
  return lines;
}

async function main(): Promise<void> {
  const { values } = parseArgs({ options: { write: { type: "boolean", default: false } } });
  const sizes = await withSlot(async () => {
    const server = await startBenchServer();
    try {
      return toolSizes(productRoutes(server.commands));
    } finally {
      await server.close();
    }
  }, { label: "bench:core" });
  const scores = derivedCoreScores();
  const next = updateFill(CORE_FILL, scores, sizes, CORE_LIMITS);
  for (const line of coreReport(scores, sizes, next)) console.log(line);
  if (sameMembers(next, CORE_FILL)) {
    console.log(`the core fill is current: ${CORE_FILL.join(", ")}`);
    return;
  }
  console.log(`the core fill changes: ${CORE_FILL.join(", ")} -> ${next.join(", ")}`);
  if (values.write) {
    writeFileSync(CORE_FILE, coreFile(next));
    console.log(`wrote ${CORE_FILE}`);
  } else {
    console.log(`run ${CORE_WRITE_COMMAND} to write it`);
    process.exitCode = 1;
  }
}

if (process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1]) await main();
