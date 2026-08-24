/**
 * Tier 5: frontend behaviour.
 *
 * The tests that matter most here are the failure ones. A green-path test proves
 * the component renders; the 503 test proves the tool still works when Yahoo is
 * down, which is the scenario that actually decides whether a live demo survives.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import App from "../App";
import { americanCompareFixture, server } from "./server";

const BASE = "/api/v1";

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

describe("valuation", () => {
  it("shows a price from every model", async () => {
    renderApp();

    expect(await screen.findByText("10.4506")).toBeInTheDocument();
    expect(await screen.findByText("10.4466")).toBeInTheDocument();
    expect(await screen.findByText("10.4602")).toBeInTheDocument();
  });

  it("shows a confidence interval for the simulated price only", async () => {
    renderApp();

    // Monte Carlo must always carry its error estimate.
    expect(await screen.findByText(/± 0\.0345 at 95%/)).toBeInTheDocument();
    // ...and there must be exactly one such annotation, since the other two models
    // are deterministic.
    expect(screen.getAllByText(/at 95%/)).toHaveLength(1);
  });

  it("marks the closed form as the exact reference", async () => {
    renderApp();
    expect(await screen.findByText("exact")).toBeInTheDocument();
  });

  it("renders all five Greeks", async () => {
    renderApp();
    const table = await screen.findByRole("table");
    for (const greek of ["delta", "gamma", "vega", "theta", "rho"]) {
      expect(within(table).getByRole("rowheader", { name: greek })).toBeInTheDocument();
    }
  });
});

describe("American exercise", () => {
  it("explains why two models declined instead of failing", async () => {
    server.use(
      http.post(`${BASE}/compare`, () => HttpResponse.json(americanCompareFixture)),
    );
    renderApp();

    await screen.findByText("6.0900");
    expect(await screen.findByText(/early-exercise premium/i)).toBeInTheDocument();
    expect(await screen.findByText(/Longstaff-Schwartz/i)).toBeInTheDocument();
  });
});

describe("market data outage", () => {
  it("falls back to manual entry rather than breaking the page", async () => {
    server.use(
      http.get(`${BASE}/market/:symbol`, () =>
        HttpResponse.json(
          {
            detail: "Could not reach the market data provider. Enter values manually.",
          },
          { status: 503 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText(/ticker symbol/i), "AAPL");
    await user.click(screen.getByRole("button", { name: /fetch/i }));

    expect(await screen.findByText(/enter values manually/i)).toBeInTheDocument();

    // The critical assertion: pricing is unaffected by the dead upstream.
    expect(await screen.findByText("10.4506")).toBeInTheDocument();
    expect(screen.getByLabelText("Spot price")).toBeEnabled();
  });

  it("populates spot and volatility from a successful lookup", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.type(screen.getByLabelText(/ticker symbol/i), "AAPL");
    await user.click(screen.getByRole("button", { name: /fetch/i }));

    await waitFor(() => {
      expect(screen.getByLabelText("Spot price")).toHaveValue(187.42);
    });
    expect(screen.getByLabelText("Volatility")).toHaveValue(0.2431);
  });
});

describe("validation", () => {
  it("refuses a negative volatility before making a request", async () => {
    const user = userEvent.setup();
    renderApp();

    const volatility = screen.getByLabelText("Volatility");
    await user.clear(volatility);
    await user.type(volatility, "-1");

    expect(await screen.findByRole("alert")).toHaveTextContent(/greater than 0/i);
  });
});

describe("pricing errors", () => {
  it("shows the server's explanation rather than a generic failure", async () => {
    server.use(
      http.post(`${BASE}/compare`, () =>
        HttpResponse.json(
          {
            error: "LatticeStabilityError",
            detail:
              "risk-neutral probability p=1.240000 is outside (0, 1): this lattice admits arbitrage.",
          },
          { status: 422 },
        ),
      ),
    );

    renderApp();
    expect(await screen.findByText(/admits arbitrage/i)).toBeInTheDocument();
  });
});
