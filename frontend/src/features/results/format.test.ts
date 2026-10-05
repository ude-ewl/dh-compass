import { describe, expect, it } from "vitest";

import { formatEuro, formatEuroCapital } from "./format";

describe("result cost formatters", () => {
  it("keeps capital and annualized euros distinct", () => {
    expect(formatEuroCapital(1200)).toBe("1\u202f200 €");
    expect(formatEuro(1200)).toBe("1\u202f200 €/a");
  });
});
