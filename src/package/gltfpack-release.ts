export type PlatformPin = { archive: string; archiveBytes: number; archiveSha256: string; executable: string; executableSha256: string };

export type ReleasePin = { version: string; baseUrl: string; platforms: Record<string, PlatformPin> };

export const GLTFPACK_RELEASE: ReleasePin = {
  version: "1.3",
  baseUrl: "https://github.com/zeux/meshoptimizer/releases/download/v1.3/",
  platforms: {
    "win32-x64": {
      archive: "gltfpack-windows.zip",
      archiveBytes: 1482895,
      archiveSha256: "f6e9c09d66af23da3da71b86f0652d2413e81c734e0aecd1cd3d0e6e6e8645c0",
      executable: "gltfpack.exe",
      executableSha256: "a082a0db2332908133100332caeeddaa304afcf5e8094adc755ebdea8c720984",
    },
    "linux-x64": {
      archive: "gltfpack-ubuntu.zip",
      archiveBytes: 1977681,
      archiveSha256: "0666d9dc40d60fe5b9a45f3fc24f8e6ca87112974bd5de9ca57152aa13d06017",
      executable: "gltfpack",
      executableSha256: "595441045457bf3d069ec14fa807b1034d324db003bd66ac6377977cc11e7da3",
    },
    "darwin-arm64": {
      archive: "gltfpack-macos.zip",
      archiveBytes: 1663661,
      archiveSha256: "1002fe6a437aa005eca541502c27b8d2b184f91f4ad0c6d282e3614a1e35e75a",
      executable: "gltfpack",
      executableSha256: "7ad9c7ef9960c86b68313017d255bd12289d31beb0baa7185518ea96953034f4",
    },
  },
};

export function platformKey(platform: string = process.platform, arch: string = process.arch): string {
  return `${platform}-${arch}`;
}
