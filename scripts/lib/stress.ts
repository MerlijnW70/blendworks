import { type ChildProcess, spawn } from "node:child_process";
import { availableParallelism } from "node:os";
import { Worker } from "node:worker_threads";
import { resolveBlender } from "../../src/blender.js";
import { GPU_BACKENDS } from "../../src/judge/device.js";
import { repoRoot } from "./paths.js";

export type StressOptions = { runs: number; cpu: number; blenders: number; device: "auto" | "cpu"; samples: number; resolution: number };

export const STRESS_USAGE = "usage: npm run check:stress -- [--runs n] [--cpu threads] [--blenders n] [--device auto|cpu] [--samples n] [--resolution px]";

export function defaultStress(cpus: number = availableParallelism()): StressOptions {
  return { runs: 3, cpu: Math.max(1, Math.floor(cpus / 4)), blenders: 2, device: "auto", samples: 64, resolution: 640 };
}

function whole(name: string, text: string | undefined, minimum: number): number {
  if (text === undefined || !/^\d+$/.test(text) || Number(text) < minimum) throw new Error(`--${name} needs a whole number of at least ${minimum}\n${STRESS_USAGE}`);
  return Number(text);
}

export function parseStress(argv: string[], defaults: StressOptions = defaultStress()): StressOptions {
  const options = { ...defaults };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    const value = argv[index + 1];
    index += 1;
    if (flag === "--runs") options.runs = whole("runs", value, 1);
    else if (flag === "--cpu") options.cpu = whole("cpu", value, 0);
    else if (flag === "--blenders") options.blenders = whole("blenders", value, 0);
    else if (flag === "--samples") options.samples = whole("samples", value, 1);
    else if (flag === "--resolution") options.resolution = whole("resolution", value, 16);
    else if (flag === "--device" && (value === "auto" || value === "cpu")) options.device = value;
    else throw new Error(`unknown option ${flag ?? ""}\n${STRESS_USAGE}`);
  }
  return options;
}

export function loadScript(options: Pick<StressOptions, "device" | "samples" | "resolution">): string {
  return [
    "import bpy",
    "scene = bpy.context.scene",
    "bpy.ops.mesh.primitive_monkey_add()",
    "head = bpy.context.active_object",
    "head.modifiers.new('detail', 'SUBSURF').render_levels = 3",
    "bpy.ops.object.light_add(type='SUN', location=(2, -2, 4))",
    "bpy.ops.object.camera_add(location=(0, -4, 0.6), rotation=(1.43, 0, 0))",
    "scene.camera = bpy.context.active_object",
    "scene.render.engine = 'CYCLES'",
    `scene.cycles.samples = ${options.samples}`,
    "scene.cycles.use_denoising = False",
    `scene.render.resolution_x = scene.render.resolution_y = ${options.resolution}`,
    "preferences = bpy.context.preferences.addons['cycles'].preferences",
    `for backend in (${options.device === "auto" ? GPU_BACKENDS.map((name) => JSON.stringify(name)).join(", ") + "," : ""}):`,
    "    try:",
    "        preferences.compute_device_type = backend",
    "    except TypeError:",
    "        continue",
    "    preferences.refresh_devices()",
    "    devices = [device for device in preferences.devices if device.type == backend]",
    "    if devices:",
    "        for device in devices:",
    "            device.use = True",
    "        scene.cycles.device = 'GPU'",
    "        break",
    "while True:",
    "    bpy.ops.render.render()",
  ].join("\n");
}

export type Load = { describe: string; stop(): Promise<void> };

function burner(): Worker {
  return new Worker("for (;;) {}", { eval: true });
}

function renderLoop(blender: string, script: string, isStopping: () => boolean, children: Set<ChildProcess>): void {
  if (isStopping()) return;
  const child = spawn(blender, ["--background", "--factory-startup", "--python-expr", script], { stdio: "ignore", windowsHide: true });
  children.add(child);
  child.on("error", () => children.delete(child));
  child.on("exit", () => {
    children.delete(child);
    if (!isStopping()) setTimeout(() => renderLoop(blender, script, isStopping, children), 1000);
  });
}

export function startLoad(options: StressOptions): Load {
  const workers = Array.from({ length: options.cpu }, burner);
  const children = new Set<ChildProcess>();
  let stopping = false;
  if (options.blenders > 0) {
    const blender = resolveBlender().path;
    const script = loadScript(options);
    for (let lane = 0; lane < options.blenders; lane += 1) renderLoop(blender, script, () => stopping, children);
  }
  return {
    describe: `${options.cpu} busy CPU threads and ${options.blenders} Blender render loops (Cycles, ${options.device}, ${options.samples} samples at ${options.resolution} px), outside the check's slots`,
    async stop() {
      stopping = true;
      await Promise.all(workers.map((worker) => worker.terminate()));
      await Promise.all(
        [...children].map(
          (child) =>
            new Promise<void>((done) => {
              child.once("exit", () => done());
              child.kill("SIGKILL");
            }),
        ),
      );
    },
  };
}

export type StressRun = { run: number; passed: boolean; seconds: number };

function runCheck(): Promise<boolean> {
  return new Promise((resolve) => {
    const cli = process.env["npm_execpath"];
    const viaNode = cli !== undefined && cli !== "";
    const child = spawn(viaNode ? process.execPath : "npm", [...(viaNode ? [cli] : []), "run", "--silent", "check"], {
      cwd: repoRoot,
      stdio: "inherit",
      windowsHide: true,
      shell: !viaNode && process.platform === "win32",
    });
    child.on("error", () => resolve(false));
    child.on("close", (code) => resolve(code === 0));
  });
}

export function stressSummary(runs: StressRun[], load: string): string[] {
  const passed = runs.filter((run) => run.passed).length;
  return [
    `${passed} of ${runs.length} full checks passed under load: ${load}`,
    ...runs.map((run) => `  run ${run.run}: ${run.passed ? "passed" : "FAILED"} in ${Math.floor(run.seconds / 60)}:${String(Math.round(run.seconds % 60)).padStart(2, "0")}`),
  ];
}

export async function stressMain(argv: string[]): Promise<number> {
  let options: StressOptions;
  try {
    options = parseStress(argv);
  } catch (error) {
    console.error((error as Error).message);
    return 2;
  }
  const load = startLoad(options);
  console.log(`load: ${load.describe}`);
  const runs: StressRun[] = [];
  try {
    for (let run = 1; run <= options.runs; run += 1) {
      console.log(`\nfull check ${run} of ${options.runs} under load`);
      const started = performance.now();
      const passed = await runCheck();
      runs.push({ run, passed, seconds: (performance.now() - started) / 1000 });
      if (!passed) break;
    }
  } finally {
    await load.stop();
  }
  console.log("");
  for (const line of stressSummary(runs, load.describe)) console.log(line);
  return runs.length === options.runs && runs.every((run) => run.passed) ? 0 : 1;
}
