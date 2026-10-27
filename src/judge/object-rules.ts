import type { Measurements } from "./measurements.js";
import { originResult, sizeRules, upAxis, type RuleResult } from "./shape-rules.js";
import type { AssetSpec, NamedObject } from "./spec.js";

type Listed = NonNullable<Measurements["objectList"]>["items"][number];

const LISTED = 10;

export function globPattern(glob: string): RegExp {
  const source = [...glob].map((character) => (character === "*" ? ".*" : character === "?" ? "." : character.replace(/[.+^${}()|[\]\\]/g, "\\$&"))).join("");
  return new RegExp(`^${source}$`, "s");
}

function summary(rule: string, objects: Listed[], checks: { object: Listed; result: RuleResult }[], limit: unknown): RuleResult {
  const failing = checks.filter((check) => !check.result.pass);
  const shown = failing.slice(0, LISTED).map((check) => `${check.object.name}: ${describe(check.result.measured)}`);
  if (failing.length > LISTED) shown.push(`and ${failing.length - LISTED} more`);
  return { rule, measured: { objects: objects.length, failing: shown }, limit, pass: failing.length === 0 };
}

function describe(value: unknown): string {
  if (typeof value === "number") return String(value);
  if (value !== null && typeof value === "object" && "distanceFromRequired" in value) return `${(value as { distanceFromRequired: number }).distanceFromRequired} m off`;
  return JSON.stringify(value);
}

function grouped(prefix: string, objects: Listed[], each: (object: Listed) => RuleResult[]): RuleResult[] {
  const byRule = new Map<string, { object: Listed; result: RuleResult }[]>();
  const limits = new Map<string, unknown>();
  for (const object of objects) {
    for (const result of each(object)) {
      const name = result.rule.slice(prefix.length);
      byRule.set(name, [...(byRule.get(name) ?? []), { object, result }]);
      limits.set(name, result.limit);
    }
  }
  return [...byRule.entries()].map(([name, checks]) => summary(`${prefix}${name}`, objects, checks, limits.get(name)));
}

function counted(prefix: string, name: string, measured: number, range: { min?: number | undefined; max?: number | undefined } | undefined): RuleResult[] {
  const results: RuleResult[] = [];
  if (range?.min !== undefined) results.push({ rule: `${prefix}${name}.min`, measured, limit: range.min, pass: measured >= range.min });
  if (range?.max !== undefined) results.push({ rule: `${prefix}${name}.max`, measured, limit: range.max, pass: measured <= range.max });
  return results;
}

function namedRules(entry: NamedObject, list: NonNullable<Measurements["objectList"]> | undefined, axis: "z" | "y"): RuleResult[] {
  const prefix = `objects[${entry.name}].`;
  if (list === undefined) return [{ rule: `${prefix}measured`, measured: null, limit: "a per-object measurement", pass: false }];
  const pattern = globPattern(entry.name);
  const objects = list.items.filter((item) => pattern.test(item.name));
  const results: RuleResult[] = [];
  if (list.count > list.items.length) {
    results.push({ rule: `${prefix}listed`, measured: { listed: list.items.length, objects: list.count }, limit: "every object listed", pass: false });
  }
  if (entry.required === true) {
    const names = objects.slice(0, LISTED).map((item) => item.name);
    results.push({ rule: `${prefix}required`, measured: { objects: objects.length, names }, limit: { objects: 1 }, pass: objects.length > 0 });
  }
  results.push(
    ...grouped(prefix, objects, (object) => [
      ...counted(prefix, "triangles", object.triangles, entry.triangles),
      ...sizeRules(prefix, entry.size, object.size, axis),
      ...(entry.origin === undefined ? [] : [originResult(`${prefix}origin`, entry.origin, { size: object.size, ...object.origin }, axis)]),
      ...counted(prefix, "materials", object.materials.length, entry.materials),
    ]),
  );
  return results;
}

export function objectRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const named = spec.objects?.named;
  if (named === undefined) return [];
  return named.flatMap((entry) => namedRules(entry, measurements.objectList, upAxis(spec)));
}

export function wantsObjectList(spec: AssetSpec): boolean {
  return spec.objects?.named !== undefined;
}
