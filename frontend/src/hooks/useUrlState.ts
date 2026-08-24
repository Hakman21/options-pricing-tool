/**
 * Keep the option parameters in the URL query string.
 *
 * Cheap to build, and it turns a configuration into something you can bookmark,
 * paste into an application, or link from a README. It also means the browser back
 * button does something sensible.
 */

import { useCallback, useEffect, useRef } from "react";
import { DEFAULT_OPTION, optionSchema, type OptionFormValues } from "../lib/schema";

const KEYS = [
  "spot",
  "strike",
  "time_to_expiry",
  "risk_free_rate",
  "volatility",
  "dividend_yield",
  "option_type",
  "exercise",
] as const;

/** Read parameters from the current URL, falling back to defaults for anything
 *  missing or malformed. A hand-edited URL must never break the page. */
export function readOptionFromUrl(): OptionFormValues {
  if (typeof window === "undefined") return DEFAULT_OPTION;

  const params = new URLSearchParams(window.location.search);
  if ([...params.keys()].length === 0) return DEFAULT_OPTION;

  const candidate: Record<string, unknown> = { ...DEFAULT_OPTION };
  for (const key of KEYS) {
    const value = params.get(key);
    if (value !== null) candidate[key] = value;
  }

  const parsed = optionSchema.safeParse(candidate);
  return parsed.success ? parsed.data : DEFAULT_OPTION;
}

export function useUrlState(option: OptionFormValues): void {
  // Skip the first run: writing on mount would replace a shared URL with an
  // identical one and add a pointless history entry.
  const mounted = useRef(false);

  const write = useCallback((values: OptionFormValues) => {
    const params = new URLSearchParams();
    for (const key of KEYS) params.set(key, String(values[key]));
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState(null, "", next);
  }, []);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    write(option);
  }, [option, write]);
}
