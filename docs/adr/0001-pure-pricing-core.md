# 1. The pricing library does not import the web framework

Status: accepted · 2026-08-23

## Context

The reference project this was modelled on puts Streamlit calls and pricing
mathematics in the same modules. It works, and it makes the mathematics untestable
without starting a UI.

## Decision

`src/option_pricing/` depends on NumPy and SciPy and nothing else. It has no
knowledge of HTTP, no Pydantic models, no settings object, no logging configuration.
`src/api/` imports from it; the dependency never runs the other way.

The library raises typed errors (`UnsupportedFeatureError`, `LatticeStabilityError`)
rather than returning sentinels or `NaN`. The API layer owns the mapping from those
errors to HTTP status codes, which is the only place that mapping belongs.

## Consequences

- Every pricing test runs in milliseconds with no server, no fixtures, no mocking.
  The property-based suite generates thousands of contracts per run; that would be
  impossible through a TestClient.
- The library is importable into a notebook, or publishable to PyPI, untouched.
- Cost: a small amount of translation code in `api/schemas.py`, and the option
  constraints are expressed twice - once in Pydantic, once in `OptionSpec`. The
  duplication is deliberate. Pydantic protects the HTTP boundary; the dataclass
  protects the library when it is used without one.
