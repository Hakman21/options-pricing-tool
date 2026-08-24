/**
 * Typed client for the pricing API.
 *
 * Every request URL is built from `import.meta.env.BASE_URL`, which Vite fills in
 * from `base` in vite.config.ts. That means the API host never appears in the
 * bundle: in production the Vercel edge rewrites `/projects/options-pricing-tool/
 * api/*` onto the container, and in development Vite's proxy does the same job. The
 * app is same-origin in both, so there is no CORS configuration anywhere.
 *
 * The request and response types come from `src/types/api.d.ts`, which is generated
 * from the backend's OpenAPI document and regenerated in CI. If the contract drifts,
 * `tsc` fails the build.
 */

import type { components } from "../types/api";

type Schemas = components["schemas"];

export type OptionInput = Schemas["OptionInput"];
export type ModelParams = Schemas["ModelParams"];
export type PricingResult = Schemas["PricingResultOut"];
export type CompareResponse = Schemas["CompareResponse"];
export type ComparisonRow = Schemas["ComparisonRow"];
export type ConvergenceResponse = Schemas["ConvergenceResponse"];
export type PayoffResponse = Schemas["PayoffResponse"];
export type SensitivityResponse = Schemas["SensitivityResponse"];
export type PathsResponse = Schemas["PathsResponse"];
export type MarketQuote = Schemas["MarketQuote"];
export type MetaResponse = Schemas["MetaResponse"];
export type ImpliedVolResponse = Schemas["ImpliedVolResponse"];
export type ModelId = Schemas["Model"];
export type GreekName = Schemas["SensitivityRequest"]["greek"];

export const API_BASE = `${import.meta.env.BASE_URL}api/v1`;

/**
 * An error carrying something worth showing the user.
 *
 * The backend returns two different failure shapes: its own `{error, detail}` for
 * refused-but-valid requests, and FastAPI's validation array for malformed ones.
 * Both are flattened here so the UI has exactly one thing to render.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: string;

  constructor(status: number, kind: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }

  /** True when live market data is down; the UI keeps manual entry available. */
  get isMarketDataOutage(): boolean {
    return this.status === 503;
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

async function readError(response: Response): Promise<ApiError> {
  let kind = "HttpError";
  let detail = `Request failed with status ${response.status}.`;

  try {
    const body = await response.json();

    if (typeof body?.error === "string" && typeof body?.detail === "string") {
      // The backend's own error envelope, raised from a typed pricing error.
      kind = body.error;
      detail = body.detail;
    } else if (Array.isArray(body?.detail)) {
      // FastAPI validation errors: report the field names, not the raw payload.
      kind = "ValidationError";
      detail = body.detail
        .map((issue: ValidationIssue) => {
          const field = issue.loc?.filter((p) => p !== "body").join(".") ?? "input";
          return `${field}: ${issue.msg ?? "is invalid"}`;
        })
        .join("; ");
    } else if (typeof body?.detail === "string") {
      detail = body.detail;
    }
  } catch {
    // A non-JSON body (a proxy error page, say) leaves the defaults in place.
  }

  return new ApiError(response.status, kind, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      0,
      "NetworkError",
      "Could not reach the pricing service. Check your connection and try again.",
    );
  }

  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const api = {
  meta: () => request<MetaResponse>("/meta"),

  price: (option: OptionInput, model: ModelId, params?: Partial<ModelParams>) =>
    post<PricingResult>("/price", { option, model, params }),

  compare: (option: OptionInput, params?: Partial<ModelParams>) =>
    post<CompareResponse>("/compare", { option, params }),

  convergence: (option: OptionInput, maxSteps = 200, maxPaths = 200_000) =>
    post<ConvergenceResponse>("/convergence", {
      option,
      max_steps: maxSteps,
      max_paths: maxPaths,
    }),

  payoff: (option: OptionInput) => post<PayoffResponse>("/payoff", { option }),

  sensitivity: (option: OptionInput, greek: GreekName, model: ModelId) =>
    post<SensitivityResponse>("/sensitivity", { option, greek, model }),

  paths: (option: OptionInput, nPaths = 80, nSteps = 100) =>
    post<PathsResponse>("/paths", { option, n_paths: nPaths, n_steps: nSteps }),

  impliedVol: (option: OptionInput, marketPrice: number) =>
    post<ImpliedVolResponse>("/implied-vol", {
      option,
      market_price: marketPrice,
    }),

  quote: (symbol: string) =>
    request<MarketQuote>(`/market/${encodeURIComponent(symbol.trim().toUpperCase())}`),
};
