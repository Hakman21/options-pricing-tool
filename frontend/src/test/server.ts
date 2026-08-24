/**
 * Mock API, shaped to match the real OpenAPI responses.
 *
 * The fixtures use the actual numbers the backend produces for the default
 * contract, so a test asserting "10.4506 is displayed" is asserting against the
 * real closed-form value rather than an invented one.
 */

import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const BASE = "/api/v1";

export const CLOSED_FORM_PRICE = 10.450583572185565;

const GREEKS = {
  delta: 0.6368306511756191,
  gamma: 0.018762017345846895,
  vega: 37.52403469169379,
  theta: -6.414027546438197,
  rho: 53.232481545376345,
};

export const compareFixture = {
  reference_model: "black_scholes",
  reference_price: CLOSED_FORM_PRICE,
  results: [
    {
      model: "black_scholes",
      price: CLOSED_FORM_PRICE,
      greeks: GREEKS,
      compute_ms: 0.42,
      standard_error: null,
      confidence_interval: null,
      diagnostics: { closed_form: true },
      abs_error: 0,
      rel_error: 0,
    },
    {
      model: "binomial",
      price: 10.446585,
      greeks: { ...GREEKS, gamma: 0.01877 },
      compute_ms: 10.3,
      standard_error: null,
      confidence_interval: null,
      diagnostics: { steps: 500 },
      abs_error: -0.003998,
      rel_error: -0.0003826,
    },
    {
      model: "monte_carlo",
      price: 10.46015,
      greeks: { ...GREEKS, delta: 0.6367 },
      compute_ms: 62.5,
      standard_error: 0.017624,
      confidence_interval: [10.42561, 10.4947],
      diagnostics: { paths: 200000, antithetic: true, control_variate: true },
      abs_error: 0.009566,
      rel_error: 0.0009154,
    },
  ],
  unsupported: [],
};

export const americanCompareFixture = {
  reference_model: "binomial",
  reference_price: 6.08999,
  results: [
    {
      model: "binomial",
      price: 6.08999,
      greeks: { ...GREEKS, delta: -0.3931 },
      compute_ms: 12.1,
      standard_error: null,
      confidence_interval: null,
      diagnostics: { steps: 500, exercise: "american" },
      abs_error: 0,
      rel_error: 0,
    },
  ],
  unsupported: [
    {
      model: "black_scholes",
      reason:
        "The closed form cannot capture the early-exercise premium of an American contract.",
    },
    {
      model: "monte_carlo",
      reason:
        "Valuing American exercise by simulation needs a regression method such as Longstaff-Schwartz, which is not implemented.",
    },
  ],
};

const payoffFixture = {
  spots: [40, 70, 100, 130, 160],
  payoffs: [0, 0, 0, 30, 60],
  profits: [-10.45, -10.45, -10.45, 19.55, 49.55],
  breakeven: 110.45,
  premium: CLOSED_FORM_PRICE,
  strike: 100,
  current_spot: 100,
};

const sensitivityFixture = {
  greek: "delta",
  model: "black_scholes",
  spots: [50, 75, 100, 125, 150],
  values: [0.03, 0.29, 0.637, 0.876, 0.964],
  current_spot: 100,
  strike: 100,
};

const convergenceFixture = {
  reference_price: CLOSED_FORM_PRICE,
  reference_model: "black_scholes",
  binomial: [
    { steps: 20, price: 10.351, error: -0.0993 },
    { steps: 21, price: 10.534, error: 0.0838 },
    { steps: 22, price: 10.36, error: -0.0904 },
    { steps: 23, price: 10.527, error: 0.0765 },
  ],
  monte_carlo: [
    {
      paths: 1000,
      price: 10.31,
      standard_error: 0.25,
      ci_low: 9.82,
      ci_high: 10.8,
      error: -0.14,
    },
    {
      paths: 10000,
      price: 10.49,
      standard_error: 0.079,
      ci_low: 10.34,
      ci_high: 10.65,
      error: 0.04,
    },
    {
      paths: 100000,
      price: 10.4593,
      standard_error: 0.0249,
      ci_low: 10.4105,
      ci_high: 10.5081,
      error: 0.0087,
    },
  ],
};

const pathsFixture = {
  times: [0, 0.5, 1],
  paths: [
    [100, 104.2, 111.3],
    [100, 96.4, 88.9],
  ],
  strike: 100,
  terminal_mean: 105.1,
};

export const quoteFixture = {
  symbol: "AAPL",
  spot: 187.42,
  currency: "USD",
  realised_vol_30d: 0.2431,
  as_of: "2026-08-23T09:00:00+00:00",
  cache_hit: false,
  source: "yfinance",
};

export const handlers = [
  http.post(`${BASE}/compare`, () => HttpResponse.json(compareFixture)),
  http.post(`${BASE}/payoff`, () => HttpResponse.json(payoffFixture)),
  http.post(`${BASE}/sensitivity`, () => HttpResponse.json(sensitivityFixture)),
  http.post(`${BASE}/convergence`, () => HttpResponse.json(convergenceFixture)),
  http.post(`${BASE}/paths`, () => HttpResponse.json(pathsFixture)),
  http.get(`${BASE}/market/:symbol`, () => HttpResponse.json(quoteFixture)),
];

export const server = setupServer(...handlers);
