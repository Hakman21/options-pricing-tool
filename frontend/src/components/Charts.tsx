/**
 * All four charts.
 *
 * Lazy-loaded as one module (see App.tsx) so Recharts stays out of the first paint.
 * They share axis styling and tooltip chrome, because four charts that each look
 * slightly different read as four separate widgets rather than one instrument.
 */

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";
import type {
  ConvergenceResponse,
  PathsResponse,
  PayoffResponse,
  SensitivityResponse,
} from "../lib/api";
import { axisTick, money } from "../lib/format";
import { ChartFrame } from "./Primitives";

const GRID = "#212c38";
const AXIS = "#63707e";
const BS = "#5b9be0";
const BINOM = "#4fb39a";
const MC = "#c288bc";

const axisProps = {
  stroke: AXIS,
  tick: { fill: AXIS, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: GRID },
} as const;

const tooltipProps = {
  contentStyle: {
    background: "#161e28",
    border: "1px solid #2a3644",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "#93a0ae", fontSize: 11 },
  itemStyle: { color: "#e3e9ef" },
} as const;

function Caption({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">{children}</p>;
}

/* ── payoff ─────────────────────────────────────────────────────────────── */

export function PayoffChart({ data }: { data: PayoffResponse }) {
  const rows = data.spots.map((spot, i) => ({
    spot,
    payoff: data.payoffs[i],
    profit: data.profits[i],
  }));

  return (
    <>
      <ChartFrame height={260}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
            <XAxis dataKey="spot" tickFormatter={axisTick} {...axisProps} />
            <YAxis tickFormatter={axisTick} {...axisProps} />
            <Tooltip
              {...tooltipProps}
              formatter={(v: number, name) => [
                money(v, 2),
                name === "payoff" ? "Payoff" : "P/L",
              ]}
              labelFormatter={(v: number) => `Spot ${money(v, 2)}`}
            />
            <ReferenceLine y={0} stroke={AXIS} strokeWidth={1} />
            <ReferenceLine
              x={data.strike}
              stroke={AXIS}
              strokeDasharray="4 4"
              label={{ value: "K", fill: AXIS, fontSize: 11, position: "top" }}
            />
            <ReferenceLine
              x={data.breakeven}
              stroke={BINOM}
              strokeDasharray="4 4"
              label={{
                value: "B/E",
                fill: BINOM,
                fontSize: 11,
                position: "top",
              }}
            />
            <Area
              dataKey="payoff"
              stroke={BS}
              fill={BS}
              fillOpacity={0.12}
              strokeWidth={2}
              dot={false}
            />
            <Line dataKey="profit" stroke={MC} strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Caption>
        Payoff at expiry (blue) and profit after paying the {money(data.premium, 2)}{" "}
        premium (purple). Breakeven at {money(data.breakeven, 2)}.
      </Caption>
    </>
  );
}

/* ── sensitivity ────────────────────────────────────────────────────────── */

export function SensitivityChart({
  data,
  greek,
}: {
  data: SensitivityResponse;
  greek: string;
}) {
  const rows = data.spots.map((spot, i) => ({ spot, value: data.values[i] }));

  return (
    <>
      <ChartFrame height={260}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
            <XAxis dataKey="spot" tickFormatter={axisTick} {...axisProps} />
            <YAxis tickFormatter={axisTick} {...axisProps} width={56} />
            <Tooltip
              {...tooltipProps}
              formatter={(v: number) => [v.toPrecision(5), greek]}
              labelFormatter={(v: number) => `Spot ${money(v, 2)}`}
            />
            <ReferenceLine y={0} stroke={AXIS} />
            <ReferenceLine x={data.strike} stroke={AXIS} strokeDasharray="4 4" />
            <ReferenceLine
              x={data.current_spot}
              stroke={BINOM}
              label={{
                value: "spot",
                fill: BINOM,
                fontSize: 11,
                position: "top",
              }}
            />
            <Area
              dataKey="value"
              stroke={BS}
              fill={BS}
              fillOpacity={0.1}
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Caption>
        {greek} across a range of spot prices, everything else held fixed. The dashed line
        is the strike; the green line is where the underlying is now.
      </Caption>
    </>
  );
}

/* ── convergence ────────────────────────────────────────────────────────── */

export function ConvergenceCharts({ data }: { data: ConvergenceResponse }) {
  const lattice = data.binomial.map((p) => ({
    steps: p.steps,
    price: p.price,
  }));
  const simulation = data.monte_carlo.map((p) => ({
    paths: p.paths,
    price: p.price,
    band: [p.ci_low, p.ci_high] as [number, number],
  }));

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xs font-medium tracking-wider text-ink-dim uppercase">
          Binomial lattice - deterministic oscillation
        </h3>
        <ChartFrame height={220}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={lattice}
              margin={{ top: 12, right: 12, bottom: 4, left: -8 }}
            >
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
              <XAxis
                dataKey="steps"
                tickFormatter={axisTick}
                {...axisProps}
                label={{
                  value: "steps",
                  fill: AXIS,
                  fontSize: 11,
                  position: "insideBottomRight",
                }}
              />
              <YAxis
                domain={["auto", "auto"]}
                tickFormatter={axisTick}
                {...axisProps}
                width={56}
              />
              <Tooltip
                {...tooltipProps}
                formatter={(v: number) => [money(v, 5), "Lattice price"]}
                labelFormatter={(v: number) => `${v} steps`}
              />
              <ReferenceLine
                y={data.reference_price}
                stroke={BS}
                strokeDasharray="5 4"
                strokeWidth={1.5}
                label={{
                  value: "exact",
                  fill: BS,
                  fontSize: 11,
                  position: "right",
                }}
              />
              <Line dataKey="price" stroke={BINOM} strokeWidth={1.8} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartFrame>
        <Caption>
          The error alternates sign as the step count changes, because adding a step moves
          the strike relative to the terminal nodes. The amplitude decays as 1/N - a
          monotone curve here would mean the lattice was not centred.
        </Caption>
      </div>

      {simulation.length > 0 && (
        <div>
          <h3 className="text-xs font-medium tracking-wider text-ink-dim uppercase">
            Monte Carlo - stochastic convergence
          </h3>
          <ChartFrame height={220}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={simulation}
                margin={{ top: 12, right: 12, bottom: 4, left: -8 }}
              >
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                <XAxis
                  dataKey="paths"
                  scale="log"
                  domain={["auto", "auto"]}
                  tickFormatter={axisTick}
                  {...axisProps}
                />
                <YAxis
                  domain={["auto", "auto"]}
                  tickFormatter={axisTick}
                  {...axisProps}
                  width={56}
                />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v: number | [number, number], name) =>
                    Array.isArray(v)
                      ? [`${money(v[0], 4)} - ${money(v[1], 4)}`, "95% interval"]
                      : [money(v, 5), name === "price" ? "Estimate" : String(name)]
                  }
                  labelFormatter={(v: number) => `${v.toLocaleString("en-GB")} paths`}
                />
                <ReferenceLine
                  y={data.reference_price}
                  stroke={BS}
                  strokeDasharray="5 4"
                  strokeWidth={1.5}
                  label={{
                    value: "exact",
                    fill: BS,
                    fontSize: 11,
                    position: "right",
                  }}
                />
                <Area dataKey="band" stroke="none" fill={MC} fillOpacity={0.18} />
                <Line
                  dataKey="price"
                  stroke={MC}
                  strokeWidth={1.8}
                  dot={{ r: 2.5, fill: MC }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
          <Caption>
            The shaded band is the 95% confidence interval, narrowing as 1/√n. Quadrupling
            the paths halves the width - which is why simulation is the expensive way to
            price something that has a closed form, and the only way to price something
            that does not.
          </Caption>
        </div>
      )}
    </div>
  );
}

/* ── sample paths ───────────────────────────────────────────────────────── */

export function PathsChart({ data }: { data: PathsResponse }) {
  // Recharts wants one row per x value with a column per series.
  const rows = data.times.map((t, i) => {
    const row: Record<string, number> = { t };
    data.paths.forEach((path, p) => {
      const value = path[i];
      if (value !== undefined) row[`p${p}`] = value;
    });
    return row;
  });

  return (
    <>
      <ChartFrame height={280}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
            <XAxis
              dataKey="t"
              tickFormatter={(v: number) => v.toFixed(2)}
              {...axisProps}
              label={{
                value: "years",
                fill: AXIS,
                fontSize: 11,
                position: "insideBottomRight",
              }}
            />
            <YAxis tickFormatter={axisTick} {...axisProps} width={56} />
            <ReferenceLine
              y={data.strike}
              stroke={BS}
              strokeDasharray="5 4"
              strokeWidth={1.5}
              label={{
                value: "strike",
                fill: BS,
                fontSize: 11,
                position: "right",
              }}
            />
            {data.paths.map((_, p) => (
              <Line
                key={p}
                dataKey={`p${p}`}
                stroke={MC}
                strokeOpacity={0.28}
                strokeWidth={1}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Caption>
        {data.paths.length} simulated trajectories under geometric Brownian motion.
        Pricing does not use these - for a vanilla European only the terminal value
        matters, so the engine samples it directly rather than stepping paths. They are
        drawn to show what the simulation is doing.
      </Caption>
    </>
  );
}
