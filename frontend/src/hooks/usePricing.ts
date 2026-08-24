/**
 * Data-fetching hooks.
 *
 * TanStack Query handles deduplication, caching and in-flight cancellation, which
 * matters here because the inputs are a live form: every keystroke would otherwise
 * fire a convergence sweep. Debouncing the inputs plus query-key caching means a
 * user sliding volatility back and forth pays for each distinct value once.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  type CompareResponse,
  type ConvergenceResponse,
  type GreekName,
  type ModelId,
  type OptionInput,
  type PathsResponse,
  type PayoffResponse,
  type SensitivityResponse,
} from "../lib/api";

/** Wait for the user to stop typing before spending a request on the value. */
export function useDebounced<T>(value: T, delayMs = 350): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return settled;
}

// Pricing is deterministic for a given input (the RNG is seeded), so a result never
// goes stale and there is no reason to refetch it.
const IMMUTABLE = {
  staleTime: Infinity,
  gcTime: 10 * 60 * 1000,
  refetchOnWindowFocus: false,
  // A 4xx is a considered refusal - an invalid contract, or a model that cannot
  // price this exercise style. Retrying it produces the same answer more slowly and
  // delays the explanation the user needs. Only transient failures are worth a
  // second attempt.
  retry: (failureCount: number, error: Error) =>
    error instanceof ApiError && error.status >= 400 && error.status < 500
      ? false
      : failureCount < 1,
} as const;

export function useComparison(option: OptionInput): UseQueryResult<CompareResponse> {
  return useQuery({
    queryKey: ["compare", option],
    queryFn: () => api.compare(option, { steps: 500, paths: 200_000 }),
    ...IMMUTABLE,
  });
}

export function usePayoff(option: OptionInput): UseQueryResult<PayoffResponse> {
  return useQuery({
    queryKey: ["payoff", option],
    queryFn: () => api.payoff(option),
    ...IMMUTABLE,
  });
}

export function useSensitivity(
  option: OptionInput,
  greek: GreekName,
  model: ModelId,
): UseQueryResult<SensitivityResponse> {
  return useQuery({
    queryKey: ["sensitivity", option, greek, model],
    queryFn: () => api.sensitivity(option, greek, model),
    ...IMMUTABLE,
  });
}

export function useConvergence(
  option: OptionInput,
  enabled: boolean,
): UseQueryResult<ConvergenceResponse> {
  return useQuery({
    queryKey: ["convergence", option],
    queryFn: () => api.convergence(option, 200, 200_000),
    // The heaviest endpoint by far - hundreds of lattices and a stack of
    // simulations - so it only runs when its panel is actually on screen.
    enabled,
    ...IMMUTABLE,
  });
}

export function usePaths(
  option: OptionInput,
  enabled: boolean,
): UseQueryResult<PathsResponse> {
  return useQuery({
    queryKey: ["paths", option],
    queryFn: () => api.paths(option, 80, 100),
    enabled,
    ...IMMUTABLE,
  });
}
