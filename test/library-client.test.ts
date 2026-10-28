import { readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PolyHavenClient, USER_AGENT } from "../src/mcp/library/client.js";
import { LibraryError } from "../src/mcp/library/common.js";
import { FakePolyHaven, fixture, json } from "./library-helpers.js";
import { scratchDir } from "./mcp-helpers.js";

interface ClientHarness {
  client: PolyHavenClient;
  polyHaven: FakePolyHaven;
  sleeps: number[];
  cacheDir: string;
  clock: { now: number };
}

function clientHarness(extra: { timeoutMs?: number; cacheTtlMs?: number } = {}): ClientHarness {
  const polyHaven = new FakePolyHaven();
  const sleeps: number[] = [];
  const cacheDir = join(scratchDir(), "cache");
  const clock = { now: 1_800_000_000_000 };
  const client = new PolyHavenClient({
    fetch: polyHaven.fetch,
    cacheDir,
    retries: 2,
    backoffMs: 100,
    sleep: async (ms) => {
      sleeps.push(ms);
    },
    now: () => clock.now,
    ...extra,
  });
  return { client, polyHaven, sleeps, cacheDir, clock };
}

async function refusal(promise: Promise<unknown>): Promise<LibraryError> {
  const error = await promise.then(
    () => undefined,
    (failure: unknown) => failure,
  );
  expect(error).toBeInstanceOf(LibraryError);
  return error as LibraryError;
}

describe("the Poly Haven client", () => {
  it("sends a descriptive User-Agent and handles redirects itself", async () => {
    const { client, polyHaven } = clientHarness();
    await client.assets("hdri");
    expect(USER_AGENT).toMatch(/^Blendworks\/\S+ \(.+\)$/);
    expect(polyHaven.seen).toEqual([{ url: "https://api.polyhaven.com/assets?t=hdris", userAgent: USER_AGENT, redirect: "manual" }]);
  });

  it("validates every response and refuses an unexpected shape", async () => {
    const { client, polyHaven } = clientHarness();
    const listing = fixture("assets-hdris.json") as Record<string, Record<string, unknown>>;
    polyHaven.json("https://api.polyhaven.com/assets?t=hdris", { ...listing, abandoned_parking: { ...listing["abandoned_parking"], type: "hdri" } });
    const shape = await refusal(client.assets("hdri"));
    expect(shape.code).toBe("invalid");
    expect(shape.message).toContain("abandoned_parking.type");

    polyHaven.json("https://api.polyhaven.com/assets?t=textures", { "../escape": (fixture("assets-textures.json") as Record<string, unknown>)["metal_plate"] });
    expect((await refusal(client.assets("texture"))).code).toBe("invalid");

    const files = fixture("files-abandoned_parking.json") as { hdri: Record<string, Record<string, Record<string, unknown>>> };
    const badMd5 = structuredClone(files);
    (badMd5.hdri["1k"] as Record<string, Record<string, unknown>>)["hdr"] = { ...badMd5.hdri["1k"]?.["hdr"], md5: "not-an-md5" };
    polyHaven.serveFiles("abandoned_parking", badMd5);
    expect(await client.files("abandoned_parking", "hdri")).toMatchObject({ hdri: badMd5.hdri });

    polyHaven.serveFiles("blue_photo_studio", { hdri: "nothing" });
    expect((await refusal(client.files("blue_photo_studio", "hdri"))).code).toBe("invalid");

    polyHaven.route("https://api.polyhaven.com/categories/hdris", () => new Response("<html>maintenance</html>", { status: 200 }));
    expect((await refusal(client.categories("hdri"))).message).toContain("not JSON");
    polyHaven.json("https://api.polyhaven.com/categories/models", ["outdoor"]);
    expect((await refusal(client.categories("model"))).code).toBe("invalid");
  });

  it("retries server errors with exponential backoff, then succeeds", async () => {
    const { client, polyHaven, sleeps } = clientHarness();
    let calls = 0;
    polyHaven.route("https://api.polyhaven.com/assets?t=models", () => {
      calls += 1;
      return calls < 3 ? new Response("busy", { status: 503 }) : json(fixture("assets-models.json"));
    });
    expect(Object.keys(await client.assets("model"))).toContain("Barrel_01");
    expect(calls).toBe(3);
    expect(sleeps).toEqual([100, 200]);
  });

  it("gives up after the bounded number of retries, honouring Retry-After", async () => {
    const { client, polyHaven, sleeps } = clientHarness();
    let calls = 0;
    polyHaven.route("https://api.polyhaven.com/assets?t=models", () => {
      calls += 1;
      return new Response("slow down", { status: 429, headers: { "retry-after": "2" } });
    });
    const error = await refusal(client.assets("model"));
    expect(calls).toBe(3);
    expect(sleeps).toEqual([2000, 2000]);
    expect(error.message).toBe("HTTP 429 for https://api.polyhaven.com/assets?t=models after 3 attempts");
  });

  it("does not retry a missing asset", async () => {
    const { client, polyHaven, sleeps } = clientHarness();
    const error = await refusal(client.info("no_such_asset"));
    expect(error.code).toBe("not_found");
    expect(polyHaven.requested("https://api.polyhaven.com/info/no_such_asset")).toHaveLength(1);
    expect(sleeps).toEqual([]);
  });

  it("times out a request that stalls, and retries it", async () => {
    const { client, polyHaven } = clientHarness({ timeoutMs: 30 });
    polyHaven.route(
      "https://api.polyhaven.com/assets?t=hdris",
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        }),
    );
    const error = await refusal(client.assets("hdri"));
    expect(error.code).toBe("offline");
    expect(error.message).toBe("cannot reach api.polyhaven.com after 3 attempts (no data arrived within the timeout)");
    expect(polyHaven.requested("https://api.polyhaven.com/assets")).toHaveLength(3);
  });

  it("reports no network clearly", async () => {
    const { client, polyHaven } = clientHarness();
    polyHaven.offline = true;
    const error = await refusal(client.assets("hdri"));
    expect(error.code).toBe("offline");
    expect(error.message).toBe("cannot reach api.polyhaven.com after 3 attempts (ENOTFOUND: getaddrinfo ENOTFOUND api.polyhaven.com)");
  });

  it("caches listings on disk until they expire", async () => {
    const { client, polyHaven, cacheDir, clock } = clientHarness({ cacheTtlMs: 60_000 });
    await client.assets("hdri");
    expect(readdirSync(cacheDir)).toEqual(["assets-hdris.json"]);
    polyHaven.offline = true;
    clock.now += 59_000;
    expect(Object.keys(await client.assets("hdri"))).toContain("abandoned_parking");
    clock.now += 2_000;
    expect((await refusal(client.assets("hdri"))).code).toBe("offline");
    polyHaven.offline = false;
    await client.assets("hdri");
    expect(polyHaven.requested("https://api.polyhaven.com/assets?t=hdris")).toHaveLength(5);
  });

  it("refetches a cache file that is corrupt or holds an unexpected shape", async () => {
    const { client, polyHaven, cacheDir, clock } = clientHarness();
    await client.categories("hdri");
    writeFileSync(join(cacheDir, "categories-hdris.json"), "{ not json");
    await client.categories("hdri");
    writeFileSync(join(cacheDir, "categories-hdris.json"), JSON.stringify({ fetchedAt: clock.now, data: { outdoor: "many" } }));
    expect((await client.categories("hdri"))["outdoor"]).toBe(705);
    expect(polyHaven.requested("https://api.polyhaven.com/categories/hdris")).toHaveLength(3);
  });

  it("follows a redirect between Poly Haven hosts", async () => {
    const { client, polyHaven } = clientHarness();
    polyHaven.route("https://api.polyhaven.com/info/abandoned_parking", () => new Response(null, { status: 302, headers: { location: "https://cdn.polyhaven.com/mirror/info/abandoned_parking" } }));
    polyHaven.json("https://cdn.polyhaven.com/mirror/info/abandoned_parking", fixture("info-abandoned_parking.json"));
    expect((await client.info("abandoned_parking")).name).toBe("Abandoned Parking");
  });

  it("refuses a redirect to a foreign host without following it", async () => {
    for (const location of ["https://evil.example/assets", "http://api.polyhaven.com/assets?t=hdris", "https://api.polyhaven.com.evil.example/x", "https://user:pw@api.polyhaven.com/x"]) {
      const { client, polyHaven } = clientHarness();
      polyHaven.route("https://api.polyhaven.com/assets?t=hdris", () => new Response(null, { status: 301, headers: { location } }));
      const error = await refusal(client.assets("hdri"));
      expect(error.code).toBe("refused");
      expect(error.message).toContain("refused a redirect from api.polyhaven.com");
      expect(polyHaven.seen.map((request) => request.url)).toEqual(["https://api.polyhaven.com/assets?t=hdris"]);
    }
  });

  it("refuses ids that are not Poly Haven ids before any request", async () => {
    const { client, polyHaven } = clientHarness();
    for (const id of ["../etc", "..", "a/b", "a\\b", "", ".hidden", "x".repeat(81), "abandoned_parking?t=1", "C:evil"]) {
      expect((await refusal(client.info(id))).code).toBe("refused");
      expect((await refusal(client.files(id, "hdri"))).code).toBe("refused");
    }
    expect(polyHaven.seen).toEqual([]);
  });
});
