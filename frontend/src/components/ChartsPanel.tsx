/**
 * Lazy-loaded chart host.
 *
 * Its only job is to pull Recharts into a separate chunk and pick the right chart
 * for the selected tab. Keeping the switch here rather than in App.tsx means the
 * chart library is never in the critical path for first paint.
 */

import { ConvergenceCharts, PathsChart, PayoffChart, SensitivityChart } from "./Charts";
import { Spinner } from "./Primitives";
import type {
  ConvergenceResponse,
  PathsResponse,
  PayoffResponse,
  SensitivityResponse,
} from "../lib/api";

export default function ChartsPanel({
  tab,
  greek,
  payoff,
  sensitivity,
  convergence,
  paths,
  loading,
}: {
  tab: "payoff" | "sensitivity" | "convergence" | "paths";
  greek: string;
  payoff?: PayoffResponse;
  sensitivity?: SensitivityResponse;
  convergence?: ConvergenceResponse;
  paths?: PathsResponse;
  loading: boolean;
}) {
  const ready =
    (tab === "payoff" && payoff) ||
    (tab === "sensitivity" && sensitivity) ||
    (tab === "convergence" && convergence) ||
    (tab === "paths" && paths);

  if (!ready) {
    return (
      <div className="flex h-[260px] items-center justify-center">
        <Spinner
          label={
            tab === "convergence"
              ? "Building lattices and running simulations"
              : "Computing"
          }
        />
      </div>
    );
  }

  return (
    <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
      {tab === "payoff" && payoff && <PayoffChart data={payoff} />}
      {tab === "sensitivity" && sensitivity && (
        <SensitivityChart data={sensitivity} greek={greek} />
      )}
      {tab === "convergence" && convergence && <ConvergenceCharts data={convergence} />}
      {tab === "paths" && paths && <PathsChart data={paths} />}
    </div>
  );
}
