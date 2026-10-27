import { describe, expect, it } from "vitest";
import { ZipError, readZipEntry } from "../../src/package/zip.js";
import { zipOf } from "./zip-fixture.js";

const PAYLOAD = new TextEncoder().encode("gltfpack ".repeat(200));
const LIMIT = 1_000_000;

describe("reading one file from a zip archive", () => {
  it("unpacks a deflated and a stored entry and checks their checksums", () => {
    for (const method of [8, 0] as const) {
      const archive = zipOf([{ name: "other.txt", data: new Uint8Array([1]) }, { name: "gltfpack", data: PAYLOAD, method }]);
      expect(readZipEntry(archive, "gltfpack", LIMIT)).toEqual(PAYLOAD);
    }
  });

  it("refuses a missing entry, a duplicate, a wrong checksum, encryption and an unpacked size over the limit", () => {
    expect(() => readZipEntry(zipOf([{ name: "a", data: PAYLOAD }]), "gltfpack", LIMIT)).toThrow("no gltfpack");
    expect(() => readZipEntry(zipOf([{ name: "gltfpack", data: PAYLOAD }, { name: "gltfpack", data: PAYLOAD }]), "gltfpack", LIMIT)).toThrow("twice");
    expect(() => readZipEntry(zipOf([{ name: "gltfpack", data: PAYLOAD, checksum: 1 }]), "gltfpack", LIMIT)).toThrow("fails its checksum");
    expect(() => readZipEntry(zipOf([{ name: "gltfpack", data: PAYLOAD, flags: 1 }]), "gltfpack", LIMIT)).toThrow("encrypted");
    expect(() => readZipEntry(zipOf([{ name: "gltfpack", data: PAYLOAD }]), "gltfpack", 100)).toThrow("more than the 100 allowed");
  });

  it("refuses a path-like entry name instead of matching its last part", () => {
    expect(() => readZipEntry(zipOf([{ name: "../gltfpack", data: PAYLOAD }]), "gltfpack", LIMIT)).toThrow(ZipError);
  });

  it("refuses data that is not a zip file", () => {
    expect(() => readZipEntry(new Uint8Array(10), "gltfpack", LIMIT)).toThrow("too short");
    expect(() => readZipEntry(new Uint8Array(100), "gltfpack", LIMIT)).toThrow("end-of-directory");
  });

  it("refuses an entry that declares a smaller size than its data unpacks to", () => {
    const archive = zipOf([{ name: "gltfpack", data: PAYLOAD }]);
    const view = new DataView(archive.buffer);
    const central = archive.byteLength - 22 - (46 + 8);
    view.setUint32(central + 24, 10, true);
    expect(() => readZipEntry(archive, "gltfpack", LIMIT)).toThrow();
  });
});
