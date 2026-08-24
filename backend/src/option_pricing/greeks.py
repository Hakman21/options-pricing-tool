"""Model-agnostic finite-difference Greeks.

Every pricer in this package supplies its own Greeks by the cheapest accurate route
available to it - analytic formulae for Black-Scholes, lattice nodes for the
binomial tree, common random numbers for Monte Carlo. This module exists as the
independent cross-check: it will differentiate *any* price function numerically, so
the test suite can confirm that each model's fast path agrees with a dumb, obviously
correct one.

Keeping the verification path separate from the production path is the whole point.
A bug in the analytic theta would otherwise be invisible.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .types import Greeks, OptionSpec


class PriceFunction(Protocol):
    def __call__(self, spec: OptionSpec) -> float: ...


# Relative for spot (scale-free), absolute for rate and volatility (already small
# numbers where a relative bump would be meaninglessly tiny near zero).
DEFAULT_SPOT_BUMP_REL = 1e-4
DEFAULT_VOL_BUMP = 1e-4
DEFAULT_RATE_BUMP = 1e-4
DEFAULT_TIME_BUMP = 1e-4


def _central(f: Callable[[float], float], x: float, h: float) -> float:
    return (f(x + h) - f(x - h)) / (2.0 * h)


def finite_difference_greeks(
    price_fn: PriceFunction,
    spec: OptionSpec,
    *,
    spot_bump_rel: float = DEFAULT_SPOT_BUMP_REL,
    vol_bump: float = DEFAULT_VOL_BUMP,
    rate_bump: float = DEFAULT_RATE_BUMP,
    time_bump: float = DEFAULT_TIME_BUMP,
) -> Greeks:
    """Differentiate ``price_fn`` numerically about ``spec``.

    Central differences throughout, which are second-order accurate and cost one
    extra evaluation per Greek compared with a forward difference. Gamma reuses the
    same spot bump as delta via the standard three-point second difference.

    The time bump is clamped so that a near-expiry contract is never pushed to a
    non-positive time to expiry, which would be outside every model's domain.
    """
    h_s = spec.spot * spot_bump_rel

    up = price_fn(spec.bumped(spot=spec.spot + h_s))
    mid = price_fn(spec)
    down = price_fn(spec.bumped(spot=spec.spot - h_s))

    delta = (up - down) / (2.0 * h_s)
    gamma = (up - 2.0 * mid + down) / (h_s * h_s)

    vega = _central(lambda v: price_fn(spec.bumped(volatility=v)), spec.volatility, vol_bump)
    rho = _central(
        lambda r: price_fn(spec.bumped(risk_free_rate=r)), spec.risk_free_rate, rate_bump
    )

    h_t = min(time_bump, spec.time_to_expiry * 0.5)
    theta = -_central(lambda t: price_fn(spec.bumped(time_to_expiry=t)), spec.time_to_expiry, h_t)

    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)
