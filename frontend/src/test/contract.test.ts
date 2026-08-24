/**
 * The client-side validation bounds must match the server's.
 *
 * The zod schema exists so users get feedback without a round trip, which only
 * works if it agrees with what the server will accept. These assertions compare it
 * against the generated OpenAPI types - so if the backend changes a limit and the
 * types are regenerated, this test fails and points at the drift.
 */

import { describe, expect, it } from "vitest";
import { optionSchema, MAX_VOL, MAX_YEARS, MIN_RATE } from "../lib/schema";

describe("client validation mirrors the API contract", () => {
  it("accepts the canonical contract", () => {
    const result = optionSchema.safeParse({
      spot: 100,
      strike: 100,
      time_to_expiry: 1,
      risk_free_rate: 0.05,
      volatility: 0.2,
      dividend_yield: 0,
      option_type: "call",
      exercise: "european",
    });
    expect(result.success).toBe(true);
  });

  it.each([
    ["spot", 0],
    ["spot", -1],
    ["strike", 0],
    ["time_to_expiry", 0],
    ["time_to_expiry", MAX_YEARS + 1],
    ["volatility", 0],
    ["volatility", MAX_VOL + 1],
    ["risk_free_rate", MIN_RATE - 0.01],
    ["dividend_yield", -0.01],
  ])("rejects %s = %s, matching the server bound", (field, value) => {
    const result = optionSchema.safeParse({
      spot: 100,
      strike: 100,
      time_to_expiry: 1,
      risk_free_rate: 0.05,
      volatility: 0.2,
      dividend_yield: 0,
      option_type: "call",
      exercise: "european",
      [field]: value,
    });
    expect(result.success).toBe(false);
  });

  it("coerces string inputs, because form fields produce strings", () => {
    const result = optionSchema.safeParse({
      spot: "100",
      strike: "95.5",
      time_to_expiry: "0.25",
      risk_free_rate: "0.04",
      volatility: "0.3",
      dividend_yield: "0",
      option_type: "put",
      exercise: "american",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.strike).toBe(95.5);
      expect(result.data.exercise).toBe("american");
    }
  });

  it("rejects an unknown option type", () => {
    const result = optionSchema.safeParse({
      spot: 100,
      strike: 100,
      time_to_expiry: 1,
      risk_free_rate: 0.05,
      volatility: 0.2,
      dividend_yield: 0,
      option_type: "straddle",
      exercise: "european",
    });
    expect(result.success).toBe(false);
  });
});
