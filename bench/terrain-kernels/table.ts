export type BenchRow = { kernel: string; one: number; four: number | null; speedup: number | null; target: number | null; exception?: "serial" | "memory-bound" | "sum" | null; pass: boolean };
export type BenchResult = { size: number; repeats: number; cpus: number; platform: string; terrain_seconds: number; shape: { basins: number; levels: number; pits_levels: number }; rows: BenchRow[] };

export const START = "<!-- speed table -->";
export const END = "<!-- end speed table -->";

function micro(value: number | null): string {
  return value === null ? "-" : value.toFixed(4);
}

export function benchTable(result: BenchResult): string {
  const lines = [
    `${result.size} x ${result.size} cells, ${result.platform}, ${result.cpus} CPUs, fastest of ${result.repeats} runs; the terrain has ${result.shape.basins} pits for lake routing and ${result.shape.levels} levels after it.`,
    "",
    "| kernel | µs per cell, 1 thread | µs per cell, 4 threads | speedup | target | holds |",
    "|---|---|---|---|---|---|",
  ];
  for (const row of result.rows) {
    const speed = row.exception === "serial" || row.speedup === null ? "one thread" : row.exception === "memory-bound" ? "memory-bound, speedup stated" : row.exception === "sum" ? "speedup judged per kernel" : "speedup >= 2.5";
    const target = row.target === null ? speed : `<= ${row.target} µs, ${speed}`;
    lines.push(`| ${row.kernel} | ${micro(row.one)} | ${micro(row.four)} | ${row.speedup === null ? "-" : `${row.speedup.toFixed(2)} x`} | ${target} | ${row.pass ? "yes" : "no"} |`);
  }
  return lines.join("\n");
}

export function recordTable(doc: string, table: string): string {
  const start = doc.indexOf(START);
  const end = doc.indexOf(END);
  if (start < 0 || end < start) throw new Error(`the document has no ${START} ... ${END} block`);
  return `${doc.slice(0, start + START.length)}\n${table}\n${doc.slice(end)}`;
}
