import { scenario } from "./scenario.js";

scenario("file A", [
  { label: "a1", holdMs: 400 },
  { label: "a2", holdMs: 400, after: "end b1" },
]);
