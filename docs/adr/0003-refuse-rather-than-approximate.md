# 3. A model that cannot price a contract refuses it

Status: accepted · 2026-08-23

## Context

Neither the Black-Scholes closed form nor a terminal-value Monte Carlo can value
American exercise. Both will happily return the European price, which is wrong by
the early-exercise premium - for a deep in-the-money put, materially wrong.

## Decision

Requesting American exercise from either model raises `UnsupportedFeatureError`,
which the API returns as a 422 naming the constraint and pointing at the binomial
model.

`/api/v1/compare` is the exception, and treats it as information rather than
failure: it returns 200 with the models that *could* price the contract, plus an
`unsupported` list carrying each refusal and its reason. Asking three models to price
an American option is a reasonable request; two of them declining is an answer.

## Consequences

- Clients must handle a 422 with a readable message. The frontend already does, and
  renders `detail` directly.
- A user who wants a European price for an American contract has to say so, which is
  the correct amount of friction.
- The same principle governs `LatticeStabilityError`: when the risk-neutral
  probability leaves `(0,1)` the tree still produces numbers, and they are
  meaningless, so it raises instead.
