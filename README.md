# Blendworks

Blender for AI agents, in three parts:

- **MCP server** (`src/mcp`): lets an agent build 3D assets in Blender, in a headless Blender it starts or in a desktop Blender.
- **Judge** (`src/judge`): checks a delivered asset against a spec in a sandboxed headless Blender, so 3D work can be hired and paid for on Solive.
- **Add-on** (`bridge/`): the same commands inside a desktop Blender. `npm run build:addon` writes `dist/blendworks-addon.zip`.

Design: [docs/DESIGN.md](docs/DESIGN.md). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

## Quickstart

You need [Node](https://nodejs.org/) 22.12 or newer and [Blender 5.2 LTS](https://www.blender.org/download/lts/). `install-claude` also needs Claude Code.

```sh
npm ci
export BLENDER=/path/to/blender       # PowerShell: $env:BLENDER = "<path to blender.exe>"
npm run doctor
npm run install-claude
```

`BLENDER` names the Blender binary; skip it when Blender is in a standard install folder. `doctor` checks Node, Blender, GPU devices, the sandbox tools and the cache, and prints what to fix. `install-claude` builds the server and adds it to Claude Code; restart Claude Code afterwards.

Then ask Claude:

> Build a 1 m wooden crate with metal corner brackets in Blender, and show me a preview render.

Judge an asset. Save this spec as `crate.spec.json`:

```json
{ "name": "crate", "format": "glb", "triangles": { "max": 800 }, "views": ["front"] }
```

`npm run fixtures` makes the test assets once and prints the folder that holds `crate.glb`:

```sh
npm run build
npm run --silent fixtures
node src/judge/bin.js judge crate.spec.json <folder>/crate.glb
```

`node src/judge/bin.js` is `blendworks` in a checkout. The judge exits 0 only when every rule passes, and writes `report.json`, `summary.txt` and `contact-sheet.png` to `artifacts/judge`.

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `BLENDER` | The Blender 5.2 binary | Standard install folders, then `PATH` |
| `BLENDWORKS_DEVICE` | Render and bake device: `auto`, `gpu` or `cpu` | `auto` |
| `BLENDWORKS_JOBS` | Most Blender processes at once, across tests, bridge tests and builds | `2` |
| `BLENDWORKS_PORT` | Port where the MCP server looks for the desktop add-on | `9876` |
| `BLENDWORKS_LIVE` | `1` runs the Poly Haven tests against the real API | off |
| `BLENDWORKS_LIBRARY_MAX_MB` | Largest library download, in MB | `300` |
| `BLENDWORKS_CACHE` | Folder for generated fixtures and locks; `npm run clean` empties it | `.cache` |
| `BLENDWORKS_VLM_PROVIDER` | Visual judge provider: `anthropic-api`, or `claude-code` (the Claude Code CLI on your own subscription, only for your own machine) | `anthropic-api` when API credentials resolve, else `claude-code` |
| `BLENDWORKS_VISUAL_MODEL` | Visual judge model when the spec names none | `claude-opus-5-5` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` | Credentials for `anthropic-api`; an `ant auth login` profile works too | none |
| `BLENDWORKS_CLAUDE` | The `claude` CLI for `claude-code` | `claude` on `PATH` |
| `BLENDWORKS_LIVE_VLM` | `1` runs the visual judge tests against the real model, through the provider above | off |
| `BLENDWORKS_PROOF_DIR` | The proof assets for those tests | `artifacts/proof` |

## Platforms

| | Windows | WSL and Linux |
|---|---|---|
| MCP server, judge, add-on | Supported | Supported |
| Judge sandbox | Job object: memory and time caps, no network isolation | `unshare -rn` cuts the network, `prlimit` caps memory |
| Skipped tests | The network-isolation test; the link tests when Windows forbids links | The Poly Haven live tests, unless `BLENDWORKS_LIVE=1` |

macOS is untested. Judge untrusted assets in WSL or Linux.

## Development

`npm run check:fast` runs the rules, the typecheck, the unit tests and the tests related to your changes. `npm run check` is the full gate. See [CONTRIBUTING.md](CONTRIBUTING.md).
