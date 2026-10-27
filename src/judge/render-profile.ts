export const TEST_RENDER_VARIABLE = "BLENDWORKS_TEST_RENDER";

export type RenderProfile = { name: "judge" | "test"; resolution: number; samples: number };

export const JUDGE_RENDER: RenderProfile = { name: "judge", resolution: 512, samples: 24 };
export const TEST_RENDER: RenderProfile = { name: "test", resolution: 128, samples: 4 };

export function renderProfile(env: NodeJS.ProcessEnv = process.env): RenderProfile {
  const value = env[TEST_RENDER_VARIABLE];
  if (value === undefined || value === "") return JUDGE_RENDER;
  if (value === "test") return TEST_RENDER;
  throw new Error(`${TEST_RENDER_VARIABLE} is for the test suite only; it is "test" or unset, not "${value}"`);
}
