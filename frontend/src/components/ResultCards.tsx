/**
 * The three model results, side by side.
 *
 * The Monte Carlo card is the one that matters: it shows the price with its
 * confidence interval, because a simulated number quoted to four decimal places
 * with no error estimate is misleading precision.
 */

import type { CompareResponse, ComparisonRow, ModelId } from "../lib/api";
import { duration, money, MODEL_COLORS, MODEL_LABELS, signed } from "../lib/format";
import { Notice, Panel, Spinner } from "./Primitives";

function Card({ row, reference }: { row: ComparisonRow; reference: number }) {
  const colour = MODEL_COLORS[row.model as ModelId];
  const isReference = row.abs_error === 0 && row.model === "black_scholes";
  const ci = row.confidence_interval;

  return (
    <div className="rounded-lg border border-line bg-raised p-4">
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: colour }}
        />
        <h3 className="text-sm font-medium text-ink">
          {MODEL_LABELS[row.model as ModelId]}
        </h3>
      </div>

      <p className="mt-3 tabular text-2xl leading-none font-medium text-ink">
        {money(row.price, 4)}
      </p>

      {ci && (
        <p className="mt-1.5 tabular text-[11px] text-mc">
          ± {money((ci[1] - ci[0]) / 2, 4)} at 95%
        </p>
      )}

      <dl className="mt-3 space-y-1 border-t border-line-soft pt-3 text-[11px]">
        <div className="flex justify-between gap-2">
          <dt className="text-ink-faint">
            {isReference ? "Reference" : "Error vs closed form"}
          </dt>
          <dd className="tabular text-ink-dim">
            {isReference ? "exact" : signed(row.abs_error, 5)}
          </dd>
        </div>
        {!isReference && (
          <div className="flex justify-between gap-2">
            <dt className="text-ink-faint">Relative</dt>
            <dd className="tabular text-ink-dim">{(row.rel_error * 100).toFixed(4)}%</dd>
          </div>
        )}
        <div className="flex justify-between gap-2">
          <dt className="text-ink-faint">Compute</dt>
          <dd className="tabular text-ink-dim">{duration(row.compute_ms)}</dd>
        </div>
        {typeof row.diagnostics?.steps === "number" && (
          <div className="flex justify-between gap-2">
            <dt className="text-ink-faint">Steps</dt>
            <dd className="tabular text-ink-dim">{row.diagnostics.steps}</dd>
          </div>
        )}
        {typeof row.diagnostics?.paths === "number" && (
          <div className="flex justify-between gap-2">
            <dt className="text-ink-faint">Paths</dt>
            <dd className="tabular text-ink-dim">
              {(row.diagnostics.paths as number).toLocaleString("en-GB")}
            </dd>
          </div>
        )}
      </dl>

      {reference !== 0 && !isReference && (
        <p className="mt-2 text-[10px] text-ink-faint">
          {Math.abs(row.rel_error) < 1e-3
            ? "Agrees with the closed form to better than 0.1%"
            : "Increase resolution to tighten the agreement"}
        </p>
      )}
    </div>
  );
}

export function ResultCards({
  data,
  isLoading,
  error,
}: {
  data?: CompareResponse;
  isLoading: boolean;
  error: Error | null;
}) {
  return (
    <Panel
      title="Valuation"
      subtitle="Identical inputs, three methods, measured against the reference."
      actions={isLoading ? <Spinner label="Pricing" /> : undefined}
    >
      {error && (
        <Notice tone="error" title="Could not price this contract">
          {error.message}
        </Notice>
      )}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.results.map((row) => (
              <Card key={row.model} row={row} reference={data.reference_price} />
            ))}
          </div>

          {(data.unsupported ?? []).length > 0 && (
            <div className="mt-4 space-y-2">
              {(data.unsupported ?? []).map((item) => (
                <Notice
                  key={item.model}
                  tone="info"
                  title={MODEL_LABELS[item.model as ModelId]}
                >
                  {item.reason}
                </Notice>
              ))}
            </div>
          )}
        </>
      )}

      {!data && !error && isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-lg border border-line bg-raised"
            />
          ))}
        </div>
      )}
    </Panel>
  );
}
