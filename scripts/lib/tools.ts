import { GLTFPACK_RELEASE, platformKey } from "../../src/package/gltfpack-release.js";
import { InstallError, installGltfpack, type Download } from "../../src/package/native-install.js";
import { selectNative } from "../../src/package/native.js";
import { cacheRoot, ensureCacheRoot } from "./paths.js";

export const TOOLS_USAGE = "usage: npm run tools:gltfpack\n  Downloads the official gltfpack release (with BasisU, for KTX2 textures) from the zeux/meshoptimizer GitHub release, checks it against the pinned sha256, and installs it in the cache folder.";

export type ToolsOptions = { env?: NodeJS.ProcessEnv; download?: Download; log?: (line: string) => void; error?: (line: string) => void };

export async function toolsMain(argv: string[], options: ToolsOptions = {}): Promise<number> {
  const env = options.env ?? process.env;
  const log = options.log ?? ((line: string) => console.log(line));
  const error = options.error ?? ((line: string) => console.error(line));
  if (argv.length > 0) {
    error(TOOLS_USAGE);
    return 2;
  }
  const root = ensureCacheRoot(cacheRoot(env));
  let installed;
  try {
    installed = await installGltfpack({ root, ...(options.download === undefined ? {} : { download: options.download }) });
  } catch (failure) {
    if (!(failure instanceof InstallError)) throw failure;
    error(`gltfpack ${GLTFPACK_RELEASE.version} was not installed (${failure.code}): ${failure.message}`);
    return 1;
  }
  log(`gltfpack ${installed.version} ${installed.status} for ${platformKey()}: ${installed.path}`);
  log(`sha256 ${installed.sha256} matches the pinned release`);
  const selection = await selectNative({ env: { ...env, BLENDWORKS_GLTFPACK: "" }, root });
  if (selection.tool === null) {
    error(`the installed binary does not work: ${selection.reason}`);
    return 1;
  }
  log(`it runs and writes KTX2: ${selection.tool.ktx2.ktx2 ? "yes" : `no (${selection.tool.ktx2.reason})`}`);
  return selection.tool.ktx2.ktx2 ? 0 : 1;
}
