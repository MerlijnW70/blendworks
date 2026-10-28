import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BOX, DIGESTED, doctorArgs, INTENT_ENGINE, intentEngineArgs, JOB_DEFAULTS, judgeCommandMain, soliveDockerArgs } from "../../scripts/lib/judge-command.js";
import { BLENDER_LINUX, buildArguments, contextFiles, DOCKERFILE, digestFrom, ensureBlenderTarball, ImageError, stampContext } from "../../scripts/lib/judge-image.js";
import { freshDir } from "./helpers.js";

const IMAGE = `blendworks-judge@sha256:${"ab".repeat(32)}`;
const JOB = { owner: "Owner1111111111111111111111111111111111111", nonce: "7", spec: "/home/dev/jobs/SPEC.md", artifact: "/home/dev/jobs/crate.glb", image: IMAGE, keypair: "/home/dev/keys/judge.json" };

function valueAfter(args: string[], flag: string): string | undefined {
  const at = args.indexOf(flag);
  return at === -1 ? undefined : args[at + 1];
}

describe("the intent-engine judge command for paid work", () => {
  it("runs an asset job in the judge image under Solive's docker sandbox, pinned by digest, with memory, CPU and /tmp caps", () => {
    const args = intentEngineArgs({ kind: "asset", ...JOB });
    expect(args.slice(0, 4)).toEqual(["npx", "-y", INTENT_ENGINE, "judge"]);
    expect(INTENT_ENGINE).toBe("@intent-engine/cli@0.1.69");
    expect(valueAfter(args, "--sandbox")).toBe("docker");
    expect(valueAfter(args, "--sandbox-image")).toBe(IMAGE);
    expect(valueAfter(args, "--sandbox-memory")).toBe(BOX.memory);
    expect(valueAfter(args, "--sandbox-cpus")).toBe(BOX.cpus);
    expect(valueAfter(args, "--sandbox-tmp")).toBe(BOX.tmp);
    expect(valueAfter(args, "--timeout")).toBe("3600");
    expect(valueAfter(args, "--verdict")).toBe("verdict.json");
    expect(valueAfter(args, "--run")).toBe("blendworks-judge asset");
    expect(args).not.toContain("--yes");
    expect(args).not.toContain("--sandbox-gpu");
    expect(args).not.toContain("--i-trust-this-work");
    expect(args).not.toContain("none");
    expect(intentEngineArgs({ kind: "asset", ...JOB, yes: true }).at(-1)).toBe("--yes");
  });

  it("runs a code job through the patch entry point, with the box it is given", () => {
    const args = intentEngineArgs({ kind: "code", ...JOB, artifact: "/home/dev/jobs/delivery.patch", box: { memory: "12g", cpus: "6", tmp: "8g" } });
    expect(valueAfter(args, "--run")).toBe("blendworks-judge patch");
    expect([valueAfter(args, "--sandbox-memory"), valueAfter(args, "--sandbox-cpus"), valueAfter(args, "--sandbox-tmp")]).toEqual(["12g", "6", "8g"]);
    expect(JOB_DEFAULTS.code.timeout).toBe(3600);
  });

  it("checks the machine once with sandbox doctor, with the same image and box", () => {
    expect(doctorArgs(IMAGE, JOB.keypair)).toEqual(["npx", "-y", INTENT_ENGINE, "sandbox", "doctor", "--keypair", JOB.keypair, "--sandbox-image", IMAGE, "--sandbox-memory", "8g", "--sandbox-cpus", "4", "--sandbox-tmp", "6g"]);
  });

  it("refuses an image that is not named by its digest", () => {
    for (const image of ["blendworks-judge:latest", "blendworks-judge", `blendworks-judge@sha256:${"ab".repeat(31)}`]) {
      expect(() => intentEngineArgs({ kind: "asset", ...JOB, image })).toThrow(/digest/);
      expect(() => doctorArgs(image)).toThrow(/digest/);
    }
    expect(IMAGE).toMatch(DIGESTED);
  });

  it("gives the container only the artifact and spec copies, read-only, a sized /tmp, and never the attestor key", () => {
    const args = soliveDockerArgs({ image: IMAGE, run: "blendworks-judge asset", work: "/tmp/copy/work", spec: "/tmp/copy/spec", artifact: "/judge/work/crate.glb", artifactSha256: "0".repeat(64), ...BOX });
    const mounts = args.flatMap((arg, index) => (args[index - 1] === "--mount" ? [arg] : []));
    expect(mounts).toEqual(["type=bind,source=/tmp/copy/work,target=/judge/work,readonly", "type=bind,source=/tmp/copy/spec,target=/judge/spec,readonly"]);
    expect(args.join(" ")).not.toContain("keys");
    expect(args).not.toContain("-v");
    expect(args).not.toContain("--volume");
    expect(args).not.toContain("--gpus");
    for (const [flag, value] of [["--network", "none"], ["--user", "65534:65534"], ["--cap-drop", "ALL"], ["--security-opt", "no-new-privileges"], ["--memory", "8g"], ["--memory-swap", "8g"], ["--cpus", "4"], ["--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=6g"], ["--ipc", "private"], ["--cgroupns", "private"], ["--log-driver", "none"], ["--entrypoint", "/bin/sh"]]) {
      expect(valueAfter(args, flag!), flag).toBe(value);
    }
    expect(args).toContain("--read-only");
    expect(args.filter((arg, index) => args[index - 1] === "--ulimit")).toEqual(["nofile=1024:1024", "core=0"]);
    expect(args.slice(-3)).toEqual([IMAGE, "-c", "blendworks-judge asset"]);
  });

  it("prints the doctor line, the preview and the attesting judge command, and the docker run line Solive starts", () => {
    const folder = freshDir("judge-command");
    const artifact = join(folder, "crate.glb");
    writeFileSync(artifact, "glb");
    const lines: string[] = [];
    expect(judgeCommandMain(["asset", "--owner", JOB.owner, "--nonce", "7", "--spec", "SPEC.md", "--artifact", artifact, "--image", IMAGE, "--keypair", JOB.keypair], (line) => lines.push(line), (line) => lines.push(line))).toBe(0);
    const commands = lines.filter((line) => !line.startsWith("#"));
    expect(commands[0]).toContain(`sandbox doctor --keypair ${JOB.keypair} --sandbox-image ${IMAGE}`);
    expect(commands[1]).toContain(`--sandbox docker --sandbox-image ${IMAGE} --sandbox-memory 8g --sandbox-cpus 4 --sandbox-tmp 6g --timeout 3600 --verdict verdict.json`);
    expect(commands[1]).not.toContain("--yes");
    expect(commands[2]).toBe(`${commands[1]} --yes`);
    expect(lines.at(-1)).toMatch(/^# Solive then starts: docker run --network none --read-only/);
    expect(lines.at(-1)).not.toContain(JOB.keypair);
    expect(judgeCommandMain(["asset", "--owner", JOB.owner], () => undefined, () => undefined)).toBe(2);
    expect(judgeCommandMain(["deploy"], () => undefined, () => undefined)).toBe(2);
  });
});

describe("the judge image build", () => {
  it("pins the base image by digest, checks Blender's published sha256, and runs CPU-only as a non-root user", () => {
    const dockerfile = readFileSync(DOCKERFILE, "utf8");
    expect(dockerfile).toMatch(/^ARG NODE_IMAGE=node:[^@\s]+@sha256:[0-9a-f]{64}$/m);
    expect(dockerfile).toContain(`ARG BLENDER_SHA256=${BLENDER_LINUX.sha256}`);
    expect(dockerfile).toContain('echo "${BLENDER_SHA256}  /tmp/blender.tar.xz" | sha256sum -c -');
    expect(dockerfile).toMatch(/^USER 65534:65534$/m);
    expect(dockerfile).not.toMatch(/^VOLUME/m);
    expect(dockerfile).toContain("BLENDWORKS_SCRATCH=/tmp/blendworks");
    expect(dockerfile).toContain("BLENDWORKS_DEVICE=cpu");
    expect(dockerfile).toContain("npm ci");
    expect(dockerfile).not.toMatch(/npm install\b/);
    expect(dockerfile).not.toMatch(/--gpus|nvidia/i);
  });

  it("builds without provenance, with the commit's time for every file, and reads the digest docker reports", () => {
    const args = buildArguments({ context: "ctx", blenderFolder: "blender", sha: "a".repeat(40), epoch: "1793168917", tag: "blendworks-judge:aaaaaaaaaaaa", metadata: "meta.json", noCache: true, extraCa: "ca.pem" });
    expect(args).toEqual(expect.arrayContaining(["--provenance=false", "--sbom=false", "--no-cache", "SOURCE_DATE_EPOCH=1793168917", "blender-download=blender", "type=image,name=blendworks-judge:aaaaaaaaaaaa,rewrite-timestamp=true", "id=extra-ca,src=ca.pem"]));
    const folder = freshDir("judge-image");
    writeFileSync(join(folder, "meta.json"), JSON.stringify({ "containerimage.digest": `sha256:${"cd".repeat(32)}` }));
    expect(digestFrom(join(folder, "meta.json"))).toBe(`sha256:${"cd".repeat(32)}`);
    writeFileSync(join(folder, "bad.json"), JSON.stringify({ "containerimage.digest": "latest" }));
    expect(() => digestFrom(join(folder, "bad.json"))).toThrow(ImageError);
  });

  it("refuses a Blender download whose sha256 is not the one blender.org publishes", async () => {
    const folder = freshDir("judge-image", "blender");
    const forged = (async () => new Response("not blender")) as unknown as typeof fetch;
    await expect(ensureBlenderTarball(folder, forged)).rejects.toThrow(/sha256/);
    expect(() => readFileSync(join(folder, BLENDER_LINUX.file))).toThrow();
  });

  it("stamps every file of the build context with the commit's time, so the checkout's own file times never reach the image", () => {
    const context = freshDir("judge-image", "context");
    mkdirSync(join(context, "entry", "judge"), { recursive: true });
    writeFileSync(join(context, "blendworks-judge"), "#!/bin/sh\n");
    writeFileSync(join(context, "entry", "judge", "entry.js"), "export {};\n");
    stampContext(context, 1793168917);
    for (const file of contextFiles(context)) expect(statSync(join(context, file)).mtimeMs, file).toBe(1793168917000);
    expect(statSync(join(context, "entry")).mtimeMs).toBe(1793168917000);
  });
});
