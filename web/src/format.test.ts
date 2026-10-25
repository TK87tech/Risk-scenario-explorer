import { describe, expect, it } from "vitest";
import { fmt, RISK_COLORS, RISK_ORDER, signed } from "./format";

describe("format helpers", () => {
  it("formats numbers with thousand separators", () => {
    expect(fmt.format(1606800)).toBe("1,606,800");
  });

  it("shows the sign of changes", () => {
    expect(signed(370800)).toBe("+370,800");
    expect(signed(-1200)).toBe("−1,200");
  });

  it("has a colour for every risk class, in order", () => {
    expect(RISK_ORDER).toEqual(["low", "moderate", "high", "very high"]);
    RISK_ORDER.forEach((c) => expect(RISK_COLORS[c]).toMatch(/^#[0-9a-f]{6}$/));
  });
});
