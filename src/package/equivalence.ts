import type { ValidationInfo } from "../judge/validator.js";
import { TEXTURE_SLOTS, type Analysis, type Box, type MaterialInfo } from "./analysis.js";

export const POSITION_BITS = 14;
export const MATRIX_TOLERANCE = 1e-5;
export const FLOAT_TOLERANCE = 1e-5;
export const COLLAPSE_SHARE = 0.01;

export type Check = { name: string; pass: boolean; detail: string };

export type Equivalence = { pass: boolean; tolerance: number; checks: Check[] };

export type EquivalenceInput = { reference: Analysis; candidate: Analysis; tolerance: number; referenceInfo?: ValidationInfo; candidateInfo?: ValidationInfo };

const LISTED = 5;

function listed(items: string[]): string {
  return items.length <= LISTED ? items.join("; ") : `${items.slice(0, LISTED).join("; ")}; and ${items.length - LISTED} more`;
}

export function diagonal(box: Box | null): number {
  if (box === null) return 0;
  return Math.hypot(box.max[0] - box.min[0], box.max[1] - box.min[1], box.max[2] - box.min[2]);
}

export function quantisationTolerance(box: Box | null, bits = POSITION_BITS): number {
  return Math.max(diagonal(box) / (2 ** bits - 1), 1e-6);
}

export function floatTolerance(box: Box | null): number {
  return Math.max(diagonal(box) * FLOAT_TOLERANCE, 1e-7);
}

function boxDistance(first: Box, second: Box): number {
  let worst = 0;
  for (let axis = 0; axis < 3; axis++) {
    worst = Math.max(worst, Math.abs(first.min[axis]! - second.min[axis]!), Math.abs(first.max[axis]! - second.max[axis]!));
  }
  return worst;
}

function sameSet(first: string[], second: string[]): { missing: string[]; extra: string[] } {
  const left = new Set(first);
  const right = new Set(second);
  return { missing: first.filter((item) => !right.has(item)), extra: second.filter((item) => !left.has(item)) };
}

function hierarchyCheck(reference: Analysis, candidate: Analysis): Check {
  const { missing, extra } = sameSet(reference.paths, candidate.paths);
  const problems = [...missing.map((path) => `missing ${path}`), ...extra.map((path) => `unexpected ${path}`)];
  for (const path of reference.paths) {
    const first = reference.matrices[path];
    const second = candidate.matrices[path];
    if (first === undefined || second === undefined) continue;
    const worst = Math.max(...first.map((value, index) => Math.abs(value - (second[index] ?? Infinity))));
    if (worst > MATRIX_TOLERANCE) problems.push(`${path} moved by ${worst.toPrecision(3)} in its transform`);
  }
  return { name: "hierarchy", pass: problems.length === 0, detail: problems.length === 0 ? `${reference.paths.length} named nodes, same tree and transforms` : listed(problems) };
}

function triangleCheck(reference: Analysis, candidate: Analysis): Check {
  const problems: string[] = [];
  if (reference.triangles !== candidate.triangles) problems.push(`${reference.triangles} against ${candidate.triangles} in total`);
  const counts = new Map(candidate.holders.map((holder) => [holder.path, holder.triangles]));
  for (const holder of reference.holders) {
    const other = counts.get(holder.path);
    if (other !== holder.triangles) problems.push(`${holder.path} has ${holder.triangles} against ${other ?? "none"}`);
  }
  return { name: "triangles", pass: problems.length === 0, detail: problems.length === 0 ? `${reference.triangles} triangles in both` : listed(problems) };
}

function boundsCheck(reference: Analysis, candidate: Analysis, tolerance: number): Check {
  const problems: string[] = [];
  let worst = 0;
  const others = new Map(candidate.holders.map((holder) => [holder.path, holder]));
  for (const holder of reference.holders) {
    const other = others.get(holder.path);
    if (holder.localBox === null || other?.localBox === undefined || other.localBox === null) {
      if (holder.localBox !== other?.localBox) problems.push(`${holder.path} has bounds in only one file`);
      continue;
    }
    const distance = boxDistance(holder.localBox, other.localBox);
    worst = Math.max(worst, distance);
    if (distance > tolerance) problems.push(`${holder.path} differs by ${distance.toPrecision(3)} m`);
  }
  if (reference.worldBox !== null && candidate.worldBox !== null) {
    const distance = boxDistance(reference.worldBox, candidate.worldBox);
    worst = Math.max(worst, distance);
    if (distance > tolerance) problems.push(`the whole asset differs by ${distance.toPrecision(3)} m`);
  } else if (reference.worldBox !== candidate.worldBox) {
    problems.push("only one file has bounds");
  }
  return {
    name: "bounds",
    pass: problems.length === 0,
    detail: problems.length === 0 ? `every node box and the whole asset within ${tolerance.toPrecision(3)} m (worst ${worst.toPrecision(3)} m)` : listed(problems),
  };
}

function materialProblems(first: MaterialInfo, second: MaterialInfo): string[] {
  const problems: string[] = [];
  if (first.alphaMode !== second.alphaMode) problems.push(`${first.name} alpha mode ${first.alphaMode} against ${second.alphaMode}`);
  if (first.doubleSided !== second.doubleSided) problems.push(`${first.name} double-sided differs`);
  for (const slot of TEXTURE_SLOTS) {
    const a = first.slots[slot];
    const b = second.slots[slot];
    if ((a === undefined) !== (b === undefined)) problems.push(`${first.name} ${slot} map is in only one file`);
    else if (a !== undefined && b !== undefined && a.texCoord !== b.texCoord) problems.push(`${first.name} ${slot} uses UV set ${a.texCoord} against ${b.texCoord}`);
  }
  return problems;
}

function materialCheck(reference: Analysis, candidate: Analysis): Check {
  const problems: string[] = [];
  const names = sameSet(reference.materials.map((material) => material.name), candidate.materials.map((material) => material.name));
  problems.push(...names.missing.map((name) => `material ${name} is missing`), ...names.extra.map((name) => `material ${name} is new`));
  const others = new Map(candidate.materials.map((material) => [material.name, material]));
  for (const material of reference.materials) {
    const other = others.get(material.name);
    if (other !== undefined) problems.push(...materialProblems(material, other));
  }
  if (reference.images.length !== candidate.images.length) problems.push(`${reference.images.length} images against ${candidate.images.length}`);
  const assigned = new Map(candidate.holders.map((holder) => [holder.path, holder.materials.join(",")]));
  for (const holder of reference.holders) {
    if (assigned.get(holder.path) !== holder.materials.join(",")) problems.push(`${holder.path} uses other materials`);
  }
  return {
    name: "materials",
    pass: problems.length === 0,
    detail: problems.length === 0 ? `${reference.materials.length} materials, ${reference.images.length} images, same texture slots and assignments` : listed(problems),
  };
}

function validatorCheck(input: EquivalenceInput): Check {
  const problems: string[] = [];
  const notes: string[] = [];
  const pairs: [string, Analysis, ValidationInfo | undefined, number][] = [
    ["reference", input.reference, input.referenceInfo, 0],
    ["candidate", input.candidate, input.candidateInfo, COLLAPSE_SHARE],
  ];
  for (const [label, analysis, info, allowed] of pairs) {
    const counted = info?.totalTriangleCount;
    if (counted === undefined) problems.push(`the validator gave no triangle count for the ${label}`);
    else if (counted > analysis.triangles) problems.push(`the validator counts ${counted} triangles in the ${label}, more than the ${analysis.triangles} its accessors declare`);
    else if (analysis.triangles - counted > analysis.triangles * allowed) problems.push(`the validator counts ${counted} triangles in the ${label}, ${analysis.triangles - counted} fewer than its accessors declare`);
    else if (counted < analysis.triangles) notes.push(`${analysis.triangles - counted} triangles of the ${label} collapse to a point or line when its positions are quantised`);
  }
  const detail = problems.length === 0 ? `the validator and the accessors count the same triangles${notes.length > 0 ? `; ${notes.join("; ")}` : ""}` : listed(problems);
  return { name: "validatorCounts", pass: problems.length === 0, detail };
}

export function compareAnalyses(input: EquivalenceInput): Equivalence {
  const checks = [
    hierarchyCheck(input.reference, input.candidate),
    triangleCheck(input.reference, input.candidate),
    boundsCheck(input.reference, input.candidate, input.tolerance),
    materialCheck(input.reference, input.candidate),
    validatorCheck(input),
  ];
  return { pass: checks.every((check) => check.pass), tolerance: input.tolerance, checks };
}
