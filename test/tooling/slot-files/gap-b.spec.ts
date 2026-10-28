import { scenario } from "./scenario.js";

scenario("file B", [{ label: "b1", holdMs: 400, after: "start a1" }]);
