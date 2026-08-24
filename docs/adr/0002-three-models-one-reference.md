# 2. Every numerical model is measured against the closed form

Status: accepted · 2026-08-23

## Context

Three models that each produce a number tell you nothing about whether any of them
is right. Two independent implementations agreeing is much stronger evidence - and
one of the three is exact.

## Decision

Black-Scholes is the reference. `/api/v1/compare` returns each model's price with its
signed and relative error against it, and `/api/v1/convergence` sweeps resolution so
the approach can be plotted.

Greeks are computed twice by different routes: analytically for the closed form,
from lattice nodes for the binomial tree, by common-random-number bumps for Monte
Carlo - and an independent finite-difference module (`greeks.py`) exists solely to
cross-check all of them in the test suite.

For American contracts there is no closed form, so a high-resolution lattice stands
in as the reference and the response says so via `reference_model`.

## Consequences

- Redundant computation, deliberately. The finite-difference path is slower and
  never used in production; it exists so that a transcription error in an analytic
  Greek cannot hide.
- Convergence tolerances are derived from the estimator's own standard error rather
  than tuned until green. Monte Carlo is asserted within **three** standard errors,
  not two: at 2σ a suite this size fails roughly one run in twenty, and a pipeline
  that goes red for no reason trains you to ignore it.
- The comparison is the product's most interesting feature as well as its strongest
  correctness argument.
