/**
 * Presentation helpers.
 *
 * The API returns raw derivatives - vega per 1.00 of volatility, theta per year -
 * because that is what the mathematics produces and what the tests check. Traders
 * quote them per vol point and per day. Converting here, at the boundary, keeps the
 * library honest and the display familiar.
 */

import type { ModelId } from "./api";

export const MODEL_LABELS: Record<ModelId, string> = {
  black_scholes: "Black-Scholes",
  binomial: "Binomial",
  monte_carlo: "Monte Carlo",
};

export const MODEL_COLORS: Record<ModelId, string> = {
  black_scholes: "#5b9be0",
  binomial: "#4fb39a",
  monte_carlo: "#c288bc",
};

export const GREEK_DESCRIPTIONS: Record<string, string> = {
  delta: "Change in option value per 1.00 move in the underlying.",
  gamma:
    "Change in delta per 1.00 move in the underlying - the convexity of the position.",
  vega: "Change in option value per 1 volatility point (shown scaled from the raw per-1.00 figure).",
  theta:
    "Value lost per calendar day, all else equal (scaled from the raw per-year figure).",
  rho: "Change in option value per 1 percentage point move in the risk-free rate.",
};

/** Fixed decimals with grouping, so columns of figures line up. */
export function money(value: number, decimals = 4): string {
  if (!Number.isFinite(value)) return "-";
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function percent(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Small numbers keep their significant figures instead of collapsing to 0.0000. */
export function compact(value: number): string {
  if (!Number.isFinite(value)) return "-";
  const magnitude = Math.abs(value);
  if (magnitude === 0) return "0";
  if (magnitude < 1e-4 || magnitude >= 1e7) return value.toExponential(2);
  return money(value, magnitude < 1 ? 5 : 3);
}

export function signed(value: number, decimals = 4): string {
  if (!Number.isFinite(value)) return "-";
  return `${value >= 0 ? "+" : ""}${money(value, decimals)}`;
}

export function duration(ms: number): string {
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Convert a raw Greek into the units practitioners actually quote.
 *
 * Delta, gamma and the raw magnitudes are left alone; vega is divided by 100 (per
 * vol point rather than per 1.00 of vol), theta by 365 (per day rather than per
 * year), and rho by 100 (per basis-point-hundred, i.e. per 1% rate move).
 */
export function displayGreek(name: string, raw: number): number {
  switch (name) {
    case "vega":
      return raw / 100;
    case "theta":
      return raw / 365;
    case "rho":
      return raw / 100;
    default:
      return raw;
  }
}

export const GREEK_UNITS: Record<string, string> = {
  delta: "per 1.00 spot",
  gamma: "per 1.00² spot",
  vega: "per vol point",
  theta: "per day",
  rho: "per 1% rate",
};

/** Axis ticks: short, and never wider than the gridline spacing allows. */
export function axisTick(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (magnitude >= 1e3) return `${(value / 1e3).toFixed(0)}k`;
  if (magnitude >= 10) return value.toFixed(0);
  if (magnitude >= 1) return value.toFixed(1);
  return value.toFixed(3);
}
