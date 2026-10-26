# Job: A faster judge (GPU, preview mode, close-ups)

Asset jobs spend most of their time in Blender renders and bakes on the CPU, while the machines that run them often have a capable GPU. Make the judge use the GPU when it can, add a quick preview mode, and add a shared close-up command, so that workers and the judge iterate faster and look at the same images.

## Required

1. **Render device:**
   - Every Blender render the judge starts picks its device from `BLENDWORKS_DEVICE`, set to `auto` (the default), `gpu` or `cpu`.
   - `auto` tries OptiX, then CUDA, HIP, Metal and oneAPI, and uses the first backend that has a usable device. Otherwise it falls back to the CPU.
   - `gpu` fails cleanly, with a reason, when no GPU backend works.
   - The chosen device and backend appear in `report.json` and in the text summary, for example `render: gpu OPTIX (NVIDIA GeForce RTX 4080)` or `render: cpu`.
2. **Sandbox with a GPU:**
   - The sandbox stays in force on every platform: no network where it is isolated today, plus a timeout and a memory limit.
   - An address-space limit (`prlimit --as`) can stop CUDA from starting, because CUDA reserves a large virtual address space. When rendering on a GPU, enforce memory another way, for example with a data-segment limit or a cgroup memory limit, and name the mechanism in the isolation line.
   - If the GPU cannot start inside the sandbox, `auto` falls back to the CPU with the original limits and says so in the summary.
   - The sandbox is never weakened to make the GPU work.
3. **Samples:**
   - Lower the judge's view samples to at most 24 and add denoising (OpenImageDenoise, or the OptiX denoiser on OptiX).
   - Keep the seed and resolution fixed, so that a re-run on the same device gives the same image.
4. **Preview mode:**
   - `blendworks judge <spec> <asset> --preview` measures and checks every rule and draws the UV layout, but renders no views.
   - The report marks the views as skipped, and the exit code depends on the rules alone.
5. **Close-ups:**
   - `blendworks closeups <asset> --out <dir> [--res <px>] [--samples <n>]` renders a fixed set of close-ups from framings fitted to the bounds. The set is a hero three-quarter view, plus a 2 × 2 grid of zoomed tiles from each of two opposite three-quarter angles, for 9 images.
   - It also writes a labelled close-up sheet.
   - It uses the same light rig, device choice and sandbox as the judge.
   - The defaults (for example 1200 px and 16 samples with denoising) are documented in the command's help.
6. **Timing:** `report.json` and the summary give the wall time of each stage (measure, render, sheet), and the close-up command prints its total time.
7. **Docs:** update the judge section of `docs/DESIGN.md` for the device choice, the preview mode and the close-up command.
8. **Tests:** they must pass on a machine without a GPU.
   - **Device choice:** the parsing of `BLENDWORKS_DEVICE`, the fallback order, and the CPU fallback when no backend is usable. Use a stubbed device list.
   - **Preview mode:** it renders no views, and the rules still decide the exit code.
   - **Close-ups:** the command produces 9 non-empty PNGs plus the sheet for a generated fixture.
   - **Sandbox:** the sandbox still blocks the network and still enforces a memory limit when the device is the CPU.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only `src/judge/`, `bridge/judge/`, `test/judge*`, `docs/DESIGN.md`, and `package.json` (scripts and `bin` only).
- Keep CPU use modest while you work: one Blender process at a time, and run the full check at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when `auto` stops falling back to the CPU, or when preview mode starts rendering views.
3. On the judge's machine (RTX 4080, WSL sandbox), the judge's own timing of the drill-rig asset (`jobs/asset-drill-rig`) is clearly faster than on the CPU with `BLENDWORKS_DEVICE=cpu`. The summary shows the GPU, and the isolation line still shows network isolation and a memory limit.
4. The judge views a close-up sheet of a real asset.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Include the timings you measured (device, stage times) in the report. Announce its sha256 to the judge.
