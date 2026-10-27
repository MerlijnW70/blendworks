import { scenario } from "./scenario.js";

scenario("file A", 0, [
  { label: "a1", holdMs: 400, gapAfterMs: 2500 },
  { label: "a2", holdMs: 400, gapAfterMs: 0 },
]);
