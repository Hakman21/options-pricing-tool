/**
 * Five Greeks by three models, with the closed form as the reference column.
 *
 * The deviation tint is the point of the table: where a numerical model disagrees
 * with the analytic value by more than a fraction of a percent, you can see it at a
 * glance rather than reading twelve numbers.
 */

import type { CompareResponse, ModelId } from "../lib/api";
import {
  compact,
  displayGreek,
  GREEK_DESCRIPTIONS,
  GREEK_UNITS,
  MODEL_COLORS,
  MODEL_LABELS,
} from "../lib/format";
import { Panel } from "./Primitives";

const GREEKS = ["delta", "gamma", "vega", "theta", "rho"] as const;

/** Green under 0.1%, amber under 1%, red above. Deviation is also printed, so the
 *  colour is reinforcement rather than the only signal. */
function deviationClass(relative: number): string {
  const magnitude = Math.abs(relative);
  if (magnitude < 1e-3) return "text-binom";
  if (magnitude < 1e-2) return "text-warn";
  return "text-danger";
}

export function GreeksTable({ data }: { data?: CompareResponse }) {
  if (!data || data.results.length === 0) return null;

  const reference =
    data.results.find((r) => r.model === "black_scholes") ?? data.results[0];
  if (!reference) return null;

  const hasReference = reference.model === "black_scholes";

  return (
    <Panel
      title="Risk sensitivities"
      subtitle={
        hasReference
          ? "Analytic values from the closed form; numerical models shown with their deviation."
          : "Read from the lattice. No closed form exists for American exercise."
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="pb-2 pr-4 text-[11px] font-medium tracking-wider text-ink-faint uppercase">
                Greek
              </th>
              {data.results.map((row) => (
                <th
                  key={row.model}
                  className="pb-2 pr-4 text-[11px] font-medium tracking-wider uppercase"
                  style={{ color: MODEL_COLORS[row.model as ModelId] }}
                >
                  {MODEL_LABELS[row.model as ModelId]}
                </th>
              ))}
              <th className="pb-2 text-[11px] font-medium tracking-wider text-ink-faint uppercase">
                Units
              </th>
            </tr>
          </thead>
          <tbody>
            {GREEKS.map((greek) => {
              const base = displayGreek(greek, reference.greeks[greek]);
              return (
                <tr key={greek} className="border-b border-line-soft last:border-0">
                  <th
                    scope="row"
                    className="py-2.5 pr-4 text-left font-medium text-ink capitalize"
                    title={GREEK_DESCRIPTIONS[greek]}
                  >
                    {greek}
                  </th>
                  {data.results.map((row) => {
                    const value = displayGreek(greek, row.greeks[greek]);
                    const isRef = row.model === reference.model;
                    const relative = base !== 0 ? (value - base) / base : 0;
                    return (
                      <td key={row.model} className="py-2.5 pr-4">
                        <span className="tabular text-ink">{compact(value)}</span>
                        {!isRef && hasReference && (
                          <span
                            className={`ml-2 tabular text-[10px] ${deviationClass(relative)}`}
                          >
                            {relative >= 0 ? "+" : ""}
                            {(relative * 100).toFixed(2)}%
                          </span>
                        )}
                      </td>
                    );
                  })}
                  <td className="py-2.5 text-[11px] text-ink-faint">
                    {GREEK_UNITS[greek]}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
        Vega and rho are shown per point rather than per unit, and theta per day rather
        than per year - the API returns raw derivatives, and the conversion happens here.
        Monte Carlo Greeks use common random numbers across each bump, without which the
        simulation noise would swamp the sensitivity being measured.
      </p>
    </Panel>
  );
}
