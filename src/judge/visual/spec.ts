import { z } from "zod";

export const DEFAULT_MODEL = "claude-opus-5-5";
export const DEFAULT_SAMPLES = 3;
export const DEFAULT_MIN_SCORE = 0.7;
export const DEFAULT_EFFORT = "high";
export const MAX_SAMPLES = 9;
export const MAX_CRITERIA = 12;
export const MAX_COMMITTEE = 5;
export const EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;
export const PROVIDERS = ["anthropic-api", "claude-code"] as const;
export const COMMITTEE_RULES = ["min", "majority"] as const;

const plainText = (max: number) =>
  z
    .string()
    .min(1)
    .max(max)
    .regex(/^[^\x00-\x1f\x7f]+$/, { message: "plain text on one line, without control characters" });

export const modelId = z.string().regex(/^[a-z0-9][a-z0-9.\-]{1,63}$/, { message: "a model id such as claude-opus-5-5" });

const criterion = z.strictObject({
  id: z.string().regex(/^[a-z][a-z0-9-]{0,39}$/, { message: "an id of lower-case letters, digits and dashes" }),
  question: plainText(300),
  weight: z.number().positive().max(100),
});

export const visualRule = z
  .strictObject({
    rubric: z
      .array(criterion)
      .min(1)
      .max(MAX_CRITERIA)
      .refine((items) => new Set(items.map((item) => item.id)).size === items.length, { message: "rubric ids must not repeat" }),
    minScore: z.number().min(0).max(1).optional(),
    samples: z.number().int().min(1).max(MAX_SAMPLES).optional(),
    required: z.boolean().optional(),
    model: modelId.optional(),
    models: z
      .array(modelId)
      .min(2)
      .max(MAX_COMMITTEE)
      .refine((items) => new Set(items).size === items.length, { message: "models must not repeat" })
      .optional(),
    committee: z.enum(COMMITTEE_RULES).optional(),
    effort: z.enum(EFFORTS).optional(),
    provider: z.enum(PROVIDERS).optional(),
  })
  .refine((rule) => rule.model === undefined || rule.models === undefined, { message: "use model or models, not both" })
  .refine((rule) => rule.committee === undefined || rule.models !== undefined, { message: "committee needs models" });

export type VisualRule = z.infer<typeof visualRule>;
export type Criterion = z.infer<typeof criterion>;
export type Effort = (typeof EFFORTS)[number];
export type ProviderName = (typeof PROVIDERS)[number];
export type CommitteeRule = (typeof COMMITTEE_RULES)[number];

export type ResolvedRule = {
  rubric: Criterion[];
  minScore: number;
  samples: number;
  required: boolean;
  models: string[];
  modelSource: "spec" | "environment" | "default";
  committee: CommitteeRule;
  effort: Effort;
};

export const MODEL_VARIABLE = "BLENDWORKS_VISUAL_MODEL";

export function resolveRule(rule: VisualRule, env: NodeJS.ProcessEnv): ResolvedRule {
  const fromEnv = env[MODEL_VARIABLE]?.trim();
  let models: string[];
  let modelSource: ResolvedRule["modelSource"];
  if (rule.models !== undefined) [models, modelSource] = [rule.models, "spec"];
  else if (rule.model !== undefined) [models, modelSource] = [[rule.model], "spec"];
  else if (fromEnv) [models, modelSource] = [[modelId.parse(fromEnv)], "environment"];
  else [models, modelSource] = [[DEFAULT_MODEL], "default"];
  return {
    rubric: rule.rubric,
    minScore: rule.minScore ?? DEFAULT_MIN_SCORE,
    samples: rule.samples ?? DEFAULT_SAMPLES,
    required: rule.required ?? false,
    models,
    modelSource,
    committee: rule.committee ?? "min",
    effort: rule.effort ?? DEFAULT_EFFORT,
  };
}
