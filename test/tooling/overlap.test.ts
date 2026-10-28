import { describe, expect, it } from "vitest";
import { maxOverlap } from "./probes.js";

describe("counting how many logged processes ran at once", () => {
  it("counts a process that logged its start and end in the same millisecond", () => {
    expect(maxOverlap([{ label: "x", start: 100, end: 100 }])).toBe(1);
    expect(maxOverlap([{ label: "x", start: 100, end: 100 }, { label: "y", start: 101, end: 101 }, { label: "z", start: 102, end: 102 }])).toBe(1);
    expect(maxOverlap([{ label: "x", start: 100, end: 200 }, { label: "y", start: 150, end: 150 }])).toBe(2);
  });

  it("does not count one process ending as the next starts as overlap, and counts real overlap", () => {
    expect(maxOverlap([{ label: "x", start: 100, end: 200 }, { label: "y", start: 200, end: 300 }])).toBe(1);
    expect(maxOverlap([{ label: "x", start: 100, end: 201 }, { label: "y", start: 200, end: 300 }, { label: "z", start: 150, end: 250 }])).toBe(3);
    expect(maxOverlap([])).toBe(0);
  });

  it("refuses a log it cannot read as intervals", () => {
    expect(maxOverlap([{ label: "x", start: Number.NaN, end: 200 }])).toBeNaN();
    expect(maxOverlap([{ label: "x", start: 300, end: 200 }])).toBeNaN();
  });
});
