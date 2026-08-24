"""Shared fixtures and Hypothesis strategies.

The strategies here define the region of parameter space the property tests explore.
They are deliberately wide enough to be interesting (deep out-of-the-money, near
expiry, high volatility) and bounded away from the degenerate corners where the
models are genuinely undefined rather than merely difficult.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from option_pricing import Exercise, OptionSpec, OptionType

# CI runs on shared hardware where a slow example can trip the deadline without
# indicating anything is wrong. Correctness is what these tests are for, not speed.
hyp_settings.register_profile(
    "default",
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
hyp_settings.register_profile("fast", max_examples=25, deadline=None)
hyp_settings.register_profile("thorough", max_examples=2000, deadline=None)
hyp_settings.load_profile("default")


def _finite(low: float, high: float) -> st.SearchStrategy[float]:
    return st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False, width=64)


spots = _finite(1.0, 1_000.0)
strikes = _finite(1.0, 1_000.0)
times = _finite(0.01, 5.0)
rates = _finite(-0.02, 0.20)
vols = _finite(0.02, 2.0)
yields = _finite(0.0, 0.10)


@st.composite
def european_specs(draw: st.DrawFn) -> OptionSpec:
    """Any European contract in a sane region of parameter space."""
    return OptionSpec(
        spot=draw(spots),
        strike=draw(strikes),
        time_to_expiry=draw(times),
        risk_free_rate=draw(rates),
        volatility=draw(vols),
        dividend_yield=draw(yields),
        option_type=draw(st.sampled_from(OptionType)),
        exercise=Exercise.EUROPEAN,
    )


@st.composite
def moderate_specs(draw: st.DrawFn) -> OptionSpec:
    """A narrower region, for tests where extreme inputs would only add noise.

    Used by the numerical cross-checks: a lattice comparison at 200% volatility one
    day from expiry tests floating-point behaviour, not the model.
    """
    return OptionSpec(
        spot=draw(_finite(20.0, 200.0)),
        strike=draw(_finite(20.0, 200.0)),
        time_to_expiry=draw(_finite(0.1, 3.0)),
        risk_free_rate=draw(_finite(0.0, 0.10)),
        volatility=draw(_finite(0.08, 0.60)),
        dividend_yield=draw(_finite(0.0, 0.05)),
        option_type=draw(st.sampled_from(OptionType)),
        exercise=Exercise.EUROPEAN,
    )


@pytest.fixture
def atm_call() -> OptionSpec:
    """The canonical worked example: S=K=100, r=5%, sigma=20%, one year."""
    return OptionSpec(
        spot=100.0,
        strike=100.0,
        time_to_expiry=1.0,
        risk_free_rate=0.05,
        volatility=0.20,
        option_type=OptionType.CALL,
    )


@pytest.fixture
def atm_put(atm_call: OptionSpec) -> OptionSpec:
    return atm_call.bumped(option_type=OptionType.PUT)
