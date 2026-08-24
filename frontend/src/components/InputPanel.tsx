/**
 * The parameter form, and the ticker lookup that can populate it.
 *
 * Validation runs on change through the zod schema, so an out-of-range value is
 * flagged before a request is made. The market data lookup is strictly additive:
 * it fills two fields and can always be ignored, and when the upstream is down the
 * form carries on working exactly as before.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { api, ApiError, type MarketQuote } from "../lib/api";
import { optionSchema, type OptionFormValues } from "../lib/schema";
import { Field, Notice, Panel, Segmented, Spinner } from "./Primitives";

const INPUT_CLASS =
  "w-full rounded border border-line bg-raised px-3 py-2 text-sm text-ink tabular " +
  "placeholder:text-ink-faint focus:border-accent focus:outline-none";

export function InputPanel({
  value,
  onChange,
}: {
  value: OptionFormValues;
  onChange: (values: OptionFormValues) => void;
}) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<OptionFormValues>({
    resolver: zodResolver(optionSchema),
    defaultValues: value,
    mode: "onChange",
  });

  const optionType = watch("option_type");
  const exercise = watch("exercise");

  const [symbol, setSymbol] = useState("");
  const [quote, setQuote] = useState<MarketQuote | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [looking, setLooking] = useState(false);

  // Push every valid change upward; invalid states simply do not propagate, so the
  // charts keep showing the last good result rather than flickering to an error.
  const submit = handleSubmit((values) => onChange(values));

  async function lookup() {
    if (!symbol.trim()) return;
    setLooking(true);
    setLookupError(null);
    try {
      const result = await api.quote(symbol);
      setQuote(result);
      setValue("spot", Number(result.spot.toFixed(2)), {
        shouldValidate: true,
      });
      if (result.realised_vol_30d) {
        setValue("volatility", Number(result.realised_vol_30d.toFixed(4)), {
          shouldValidate: true,
        });
      }
      await submit();
    } catch (error) {
      setQuote(null);
      setLookupError(
        error instanceof ApiError
          ? error.message
          : "Lookup failed. Enter the spot price and volatility manually.",
      );
    } finally {
      setLooking(false);
    }
  }

  return (
    <Panel
      title="Contract"
      subtitle="All fields are editable, with or without a live quote."
    >
      <form
        onChange={() => void submit()}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
        className="space-y-4"
      >
        {/* ── ticker lookup ─────────────────────────────────────────────── */}
        <div className="rounded border border-line-soft bg-raised/60 p-3">
          <Field label="Ticker (optional)" hint="fills spot and volatility">
            <div className="flex gap-2">
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void lookup();
                  }
                }}
                placeholder="AAPL, ^GSPC, VOD.L"
                aria-label="Ticker symbol"
                className={INPUT_CLASS}
              />
              <button
                type="button"
                onClick={() => void lookup()}
                disabled={looking || !symbol.trim()}
                className="shrink-0 rounded border border-line bg-panel px-3 py-2 text-xs font-medium text-ink-dim hover:text-ink disabled:opacity-40"
              >
                {looking ? "…" : "Fetch"}
              </button>
            </div>
          </Field>

          {looking && (
            <div className="mt-2">
              <Spinner label="Fetching quote" />
            </div>
          )}

          {quote && !looking && (
            <p className="mt-2 text-[11px] text-ink-faint">
              <span className="text-binom">●</span> {quote.symbol} at{" "}
              <span className="tabular text-ink-dim">
                {quote.spot.toFixed(2)} {quote.currency}
              </span>
              {quote.realised_vol_30d !== null && (
                <>
                  {" · 30d realised vol "}
                  <span className="tabular text-ink-dim">
                    {(quote.realised_vol_30d * 100).toFixed(1)}%
                  </span>
                </>
              )}
              {" · "}
              {quote.cache_hit ? "cached" : "fresh"} ·{" "}
              {quote.as_of.slice(0, 16).replace("T", " ")}
            </p>
          )}

          {lookupError && (
            <div className="mt-2">
              <Notice tone="warn" onDismiss={() => setLookupError(null)}>
                {lookupError}
              </Notice>
            </div>
          )}
        </div>

        {/* ── contract type ─────────────────────────────────────────────── */}
        <div className="flex flex-wrap gap-4">
          <div>
            <span className="mb-1 block text-xs font-medium tracking-wide text-ink-dim uppercase">
              Type
            </span>
            <Segmented
              label="Option type"
              value={optionType}
              onChange={(v) => {
                setValue("option_type", v, { shouldValidate: true });
                void submit();
              }}
              options={[
                { value: "call", label: "Call" },
                { value: "put", label: "Put" },
              ]}
            />
          </div>
          <div>
            <span className="mb-1 block text-xs font-medium tracking-wide text-ink-dim uppercase">
              Exercise
            </span>
            <Segmented
              label="Exercise style"
              value={exercise}
              onChange={(v) => {
                setValue("exercise", v, { shouldValidate: true });
                void submit();
              }}
              options={[
                { value: "european", label: "European" },
                { value: "american", label: "American" },
              ]}
            />
          </div>
        </div>

        {exercise === "american" && (
          <Notice tone="info">
            Only the binomial lattice prices American exercise. The closed form has no
            early-exercise term, and simulation would need Longstaff-Schwartz.
          </Notice>
        )}

        {/* ── numeric inputs ────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Spot" error={errors.spot?.message}>
            <input
              type="number"
              step="any"
              className={INPUT_CLASS}
              aria-label="Spot price"
              {...register("spot")}
            />
          </Field>
          <Field label="Strike" error={errors.strike?.message}>
            <input
              type="number"
              step="any"
              className={INPUT_CLASS}
              aria-label="Strike price"
              {...register("strike")}
            />
          </Field>
          <Field label="Expiry" hint="years" error={errors.time_to_expiry?.message}>
            <input
              type="number"
              step="any"
              className={INPUT_CLASS}
              aria-label="Time to expiry in years"
              {...register("time_to_expiry")}
            />
          </Field>
          <Field label="Volatility" hint="0.2 = 20%" error={errors.volatility?.message}>
            <input
              type="number"
              step="any"
              className={INPUT_CLASS}
              aria-label="Volatility"
              {...register("volatility")}
            />
          </Field>
          <Field
            label="Risk-free rate"
            hint="0.05 = 5%"
            error={errors.risk_free_rate?.message}
          >
            <input
              type="number"
              step="any"
              className={INPUT_CLASS}
              aria-label="Risk-free rate"
              {...register("risk_free_rate")}
            />
          </Field>
          <Field
            label="Dividend yield"
            hint="continuous"
            error={errors.dividend_yield?.message}
          >
            <input
              type="number"
              step="any"
              className={INPUT_CLASS}
              aria-label="Dividend yield"
              {...register("dividend_yield")}
            />
          </Field>
        </div>

        <p className="text-[11px] leading-relaxed text-ink-faint">
          Rates and yields are continuously compounded. Time is in years, so a three-month
          option is 0.25.
        </p>
      </form>
    </Panel>
  );
}
