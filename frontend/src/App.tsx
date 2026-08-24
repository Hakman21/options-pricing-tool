/**
 * Page composition.
 *
 * Two columns on desktop: inputs pinned left, results right. The heavy panels
 * (convergence, sample paths) sit behind tabs and their queries only run when
 * selected - a convergence sweep builds several hundred lattices, which is not
 * something to do on every keystroke.
 */

import { lazy, Suspense, useMemo, useState } from "react";
import { InputPanel } from "./components/InputPanel";
import { ResultCards } from "./components/ResultCards";
import { GreeksTable } from "./components/GreeksTable";
import { Notice, Panel, Segmented, Spinner } from "./components/Primitives";
import {
  useComparison,
  useConvergence,
  useDebounced,
  usePaths,
  usePayoff,
  useSensitivity,
} from "./hooks/usePricing";
import { readOptionFromUrl, useUrlState } from "./hooks/useUrlState";
import type { GreekName, ModelId } from "./lib/api";
import type { OptionFormValues } from "./lib/schema";

const Charts = lazy(() => import("./components/ChartsPanel"));

type Tab = "payoff" | "sensitivity" | "convergence" | "paths";

const TABS: { value: Tab; label: string }[] = [
  { value: "payoff", label: "Payoff" },
  { value: "sensitivity", label: "Sensitivity" },
  { value: "convergence", label: "Convergence" },
  { value: "paths", label: "Paths" },
];

export default function App() {
  const [option, setOption] = useState<OptionFormValues>(readOptionFromUrl);
  const [tab, setTab] = useState<Tab>("payoff");
  const [greek, setGreek] = useState<GreekName>("delta");

  useUrlState(option);

  // One debounced value feeds every query, so a burst of typing costs one round of
  // requests rather than one per character.
  const settled = useDebounced(option, 350);
  const request = useMemo(() => settled, [settled]);

  const comparison = useComparison(request);
  const payoff = usePayoff(request);
  const sensitivityModel: ModelId =
    request.exercise === "american" ? "binomial" : "black_scholes";
  const sensitivity = useSensitivity(request, greek, sensitivityModel);
  const convergence = useConvergence(request, tab === "convergence");
  const paths = usePaths(request, tab === "paths");

  return (
    <div className="min-h-screen bg-ground">
      <header className="border-b border-line">
        <div className="mx-auto max-w-[1400px] px-5 py-5 sm:px-8">
          <p className="text-[11px] tracking-[0.14em] text-ink-faint uppercase">
            Hakim Ahmed · Quantitative tooling
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold text-ink">Options Pricing Tool</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-dim">
            Black-Scholes, a binomial lattice and Monte Carlo simulation, priced from the
            same inputs and measured against each other. Every model returns all five
            Greeks; the convergence view shows the numerical methods approaching the exact
            answer.
          </p>
          <nav className="mt-3 flex flex-wrap gap-4 text-xs">
            <a
              className="text-accent hover:underline"
              href={`${import.meta.env.BASE_URL}api/docs`}
            >
              API docs
            </a>
            <a
              className="text-accent hover:underline"
              href="https://github.com/Hakman21/options-pricing-tool"
              rel="noreferrer"
            >
              Source
            </a>
          </nav>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1400px] gap-5 px-5 py-6 sm:px-8 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-6 lg:self-start">
          <InputPanel value={option} onChange={setOption} />
        </div>

        <div className="min-w-0 space-y-5">
          <ResultCards
            data={comparison.data}
            isLoading={comparison.isFetching}
            error={comparison.error}
          />

          <GreeksTable data={comparison.data} />

          <Panel
            title="Analysis"
            actions={
              <div className="flex flex-wrap items-center gap-2">
                {tab === "sensitivity" && (
                  <Segmented
                    label="Greek"
                    value={greek}
                    onChange={setGreek}
                    options={[
                      { value: "delta", label: "Δ" },
                      { value: "gamma", label: "Γ" },
                      { value: "vega", label: "ν" },
                      { value: "theta", label: "Θ" },
                      { value: "rho", label: "ρ" },
                    ]}
                  />
                )}
                <Segmented label="View" value={tab} onChange={setTab} options={TABS} />
              </div>
            }
          >
            <Suspense fallback={<Spinner label="Loading charts" />}>
              <Charts
                tab={tab}
                greek={greek}
                payoff={payoff.data}
                sensitivity={sensitivity.data}
                convergence={convergence.data}
                paths={paths.data}
                loading={
                  (tab === "payoff" && payoff.isFetching) ||
                  (tab === "sensitivity" && sensitivity.isFetching) ||
                  (tab === "convergence" && convergence.isFetching) ||
                  (tab === "paths" && paths.isFetching)
                }
              />
            </Suspense>
          </Panel>

          {comparison.data?.reference_model === "binomial" && (
            <Notice tone="info" title="American exercise">
              With no closed form available, a high-resolution lattice is standing in as
              the reference price.
            </Notice>
          )}

          <footer className="pb-8 text-[11px] leading-relaxed text-ink-faint">
            Educational tool. Prices assume geometric Brownian motion with constant
            volatility and a continuous dividend yield - real markets exhibit a volatility
            smile that this model does not capture. Not investment advice.
          </footer>
        </div>
      </main>
    </div>
  );
}
