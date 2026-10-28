# Job: One vocabulary, one mesh I/O layer and lean tool schemas across the bridge

The bridge has grown to well over a hundred commands written by many jobs. An audit found the seams: five copies of "read coordinates and apply the world matrix" with float32 and float64 differences, four vertex-group weight readers, two attribute writers; commands that write vertex positions while ignoring shape keys and modifiers (and `abrade` dropping extra UV layers, vertex groups and attributes); singular or mirrored object matrices raising raw `LinAlgError` or flipping normals; range pairs accepted in reverse order; `required` fields with dead defaults; `schema.length(description, default, maximum)` easy to misread; the same idea named `amplitude`, `height` or `depth`, `scale` meaning a wavelength in one command and a multiplier in another, slope measured from vertical in one place and talus from horizontal in another, seeds ranging to 2^31 or to 10^6; and tool schemas so large (`material_procedural` 28.5 KB, `material_layer` 32 KB) that they cannot fit an MCP core listing. Make the bridge consistent.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`meshio` module:** world and local points (one precision policy, documented), vertex-group weights (vectorised), point and corner attribute read/write, a singular-matrix and mirrored-matrix aware object transform (inverse-transpose normals with the determinant sign), and a `require_plain_mesh` guard that refuses or correctly handles shape keys and modifiers; every duplicate in the bridge replaced by it.
2. **Vertex-writing commands** (`noise_displace`, heightfield storage, `abrade`, `chip`, `fracture` write-back, and any other found) either apply to all shape-key blocks or refuse with a clear message, and keep every UV layer, vertex group and attribute they do not intend to drop.
3. **Schema vocabulary:** `schema.seed()`, `ordered_pair()`, explicit `exclusive_with` / `requires` rules validated before any bpy access, a renamed `length` helper whose default cannot be read as a minimum, a documented glossary (amplitude, height, depth, scale versus wavelength, angles and their reference direction, seeds), and the commands renamed or aliased to it with deprecation aliases that keep old argument names working for one release and say so.
4. **Lean schemas:** tool descriptions and schemas for the largest commands split or restructured (for example per-preset option objects, enums instead of prose, shared definitions) so no single tool exceeds a stated size and the core listing can include the material tools; the routing benchmark does not drop.
5. **Metadata audit:** a test fails when a command lacks family, intents or nearest, or when `nearest` names an unknown tool.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include shape-keyed, mirrored, zero-scale and multi-UV fixtures for each vertex-writing command, reversed range pairs, and a size test on every tool schema. All existing examples give the same results (report).

## Rules

- Follow `CONTRIBUTING.md`. Behaviour of correct calls does not change except where the old behaviour was a bug, listed in the delivery.
- **Allowed files:** `bridge/blendworks_bridge/**` (not `bridge/judge/**`), `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Files shared with other open jobs:** parallel bridge jobs (turntable-lighting, repair-gate) add new modules; this job touches many existing ones, so it runs when no other bridge-heavy job is open, and rebases last.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge reruns every example with unchanged summaries, and lists the default MCP core and its byte size before and after.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
