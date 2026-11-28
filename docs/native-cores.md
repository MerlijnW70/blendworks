# Prebuilt native cores

The terrain core (`native/`, see `terrain-core.md`) is Rust. Users do not need Rust: the npm package and the Blender add-on carry compiled cores, the way NumPy and Pillow carry compiled code. Only contributors who change `native/` need cargo.

## Supported platforms

| Platform key | System | Rust target | Library | Baseline |
| --- | --- | --- | --- | --- |
| `win32-x64` | Windows x64 | `x86_64-pc-windows-msvc` | `blendworks_core.dll` | Windows 10 |
| `linux-x64` | Linux x64 | `x86_64-unknown-linux-gnu` | `libblendworks_core.so` | glibc 2.31 (built in Debian bullseye) |
| `darwin-arm64` | macOS on Apple silicon | `aarch64-apple-darwin` | `libblendworks_core.dylib` | macOS 14 runner |
| `darwin-x64` | macOS on Intel | `x86_64-apple-darwin` | `libblendworks_core.dylib` | macOS 13 runner |

Any other system or architecture (Linux on arm64, Windows on arm64) has no prebuilt core and runs the Python reference kernels; the status says so.

## Install without Rust

Install the npm package or the add-on zip. Nothing else is needed. The core for your platform is bundled; on start the loader checks its sha256 against `manifest.json` and loads it only if they match. macOS cores are built in CI but untested by the project.

## How a core is chosen

`terrain_core.core()` (once per process) tries, in order:

1. the file named by `BLENDWORKS_NATIVE_LIB`, reported as source `environment`;
2. a developer build, `native/target/release/<library>`, reported as `developer`;
3. the bundled core for this platform and architecture, reported as `bundled`: `native/dist/` in a checkout or the npm package, `blendworks_bridge/native/` in the add-on. Its file is hashed and compared with the manifest entry. A match is `loaded`, no file or no entry is `missing`, a different hash is `mismatched` and the file is refused and never loaded.

With no usable core Blendworks runs the Python reference kernels. It prints one line per session, `blendworks: <reason>; using the Python reference kernels (the Python reference kernels run roughly 100 times slower than the native core)`. `blender_scene_info` and `blender_erode` return the same facts under `native_core`: `engine` (`native` or `python`), `source`, `check` (`loaded`, `missing`, `mismatched`), and for the fallback `reason` and `slowdown`. Where the core is required (`BLENDWORKS_NATIVE=require` or the judge image marker), a core that does not load is an error instead.

## Contributor build

Needs Rust 1.63 or newer. `npm run build:native` builds `native/target/release/<library>` offline from the lock file; the loader prefers it over a bundled core.

## Cut a release with the cores

1. Run the `native-cores` workflow (GitHub Actions, on a `v*` tag or by hand). Its matrix builds the four targets with the pinned Rust toolchain (`RUST_VERSION` in the workflow), `--offline --locked`, Linux inside Debian bullseye for the glibc 2.31 baseline. Each platform uploads an artifact `core-<key>`; the `manifest` job gathers them, writes `manifest.json` (sha256 and size of each file, the source commit) and fails if a platform is missing. The result is the artifact `native-cores`.
2. Download it into a folder, then `BLENDWORKS_RELEASE=1 npm run native:stage -- <folder>` (or `--release`) copies the cores into `native/dist/` and checks them. A missing platform is an error in release mode and is named. Without release mode only the platforms present are staged, for a build that targets one platform: `npm run build:native && npm run native:stage` stages the local core.
3. `npm pack` (its `prepack` runs `npm run native:verify`, which fails on a hash mismatch, and on a missing platform under `BLENDWORKS_RELEASE=1`) and `BLENDWORKS_RELEASE=1 npm run build:addon` pack the same `native/dist/`. The add-on carries the cores under `blendworks_bridge/native/`.

`native/dist/` is generated and not committed.
