/**
 * Small shared building blocks.
 *
 * Kept in one file because none of them is big enough to justify its own, and
 * having the visual vocabulary in a single place is what stops the panels drifting
 * apart as the app grows.
 */

import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-line bg-panel ${className}`}
      aria-label={title}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line-soft px-5 py-3.5">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-dim">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium tracking-wide text-ink-dim uppercase">
          {label}
        </span>
        {hint && <span className="text-[11px] text-ink-faint">{hint}</span>}
      </span>
      {children}
      {/* Errors are announced, not just coloured - colour alone is not an
          accessible way to signal a problem. */}
      {error && (
        <span role="alert" className="mt-1 block text-xs text-danger">
          {error}
        </span>
      )}
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string; disabled?: boolean }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-md border border-line bg-raised p-0.5"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            className={`rounded px-3 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              selected ? "bg-accent/15 text-accent" : "text-ink-dim hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
  onDismiss,
}: {
  tone?: "info" | "warn" | "error";
  title?: string;
  children: ReactNode;
  onDismiss?: () => void;
}) {
  const border = {
    info: "border-l-accent",
    warn: "border-l-warn",
    error: "border-l-danger",
  }[tone];

  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex items-start gap-3 rounded border border-line border-l-2 bg-raised px-4 py-3 text-sm ${border}`}
    >
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium text-ink">{title}</p>}
        <div className="text-ink-dim">{children}</div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 text-ink-faint hover:text-ink"
        >
          ×
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-ink-faint" role="status">
      <span
        aria-hidden
        className="h-3 w-3 animate-spin rounded-full border-2 border-line border-t-accent"
      />
      {label}
    </div>
  );
}

/** A fixed-height placeholder, so a chart appearing does not shift the page. */
export function ChartFrame({
  height = 260,
  children,
}: {
  height?: number;
  children: ReactNode;
}) {
  return (
    <div style={{ height }} className="w-full">
      {children}
    </div>
  );
}
