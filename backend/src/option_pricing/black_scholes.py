"""Black-Scholes-Merton closed form with continuous dividend yield.

This module is the reference implementation. Because the formula is exact, every
number it produces doubles as ground truth for the numerical models: the binomial
lattice and Monte Carlo simulation are both tested against it, and the web UI plots
their convergence toward it.

Carrying the dividend yield ``q`` costs nothing here and makes the tool correct for
index options, which is why it is present from the start rather than bolted on.
"""

from __future__ import annotations

import math
import time

from scipy.optimize import brentq
from scipy.stats import norm

from .errors import ConvergenceError, UnsupportedFeatureError
from .types import Greeks, Model, OptionSpec, OptionType, PricingResult

__all__ = ["greeks", "implied_volatility", "price", "price_with_greeks"]

# Widest volatility bracket the implied-vol solver will search. 500% annualised is
# far beyond anything quoted on a listed option; if the root is not in here, the
# input price is almost certainly outside the no-arbitrage bounds.
_IV_LOWER = 1e-6
_IV_UPPER = 5.0


def _guard_european(spec: OptionSpec) -> None:
    if spec.is_american:
        raise UnsupportedFeatureError(
            "Black-Scholes prices European exercise only. An American contract has "
            "an early-exercise premium this formula cannot capture; use the binomial "
            "model instead."
        )


def _d1_d2(spec: OptionSpec) -> tuple[float, float]:
    """The two standardised log-moneyness terms every formula here is built from."""
    s, k = spec.spot, spec.strike
    t, r, q, vol = spec.time_to_expiry, spec.risk_free_rate, spec.dividend_yield, spec.volatility
    vol_root_t = vol * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * vol * vol) * t) / vol_root_t
    return d1, d1 - vol_root_t


def price(spec: OptionSpec) -> float:
    """Closed-form price of a European option."""
    _guard_european(spec)
    d1, d2 = _d1_d2(spec)
    disc_r = math.exp(-spec.risk_free_rate * spec.time_to_expiry)
    disc_q = math.exp(-spec.dividend_yield * spec.time_to_expiry)

    if spec.option_type is OptionType.CALL:
        return float(spec.spot * disc_q * norm.cdf(d1) - spec.strike * disc_r * norm.cdf(d2))
    return float(spec.strike * disc_r * norm.cdf(-d2) - spec.spot * disc_q * norm.cdf(-d1))


def greeks(spec: OptionSpec) -> Greeks:
    """Analytic Greeks.

    All five fall out of the same ``d1``, ``d2`` and standard normal density that the
    price already needs, so they are essentially free once the price is computed.
    """
    _guard_european(spec)
    d1, d2 = _d1_d2(spec)
    s, k = spec.spot, spec.strike
    t, r, q, vol = spec.time_to_expiry, spec.risk_free_rate, spec.dividend_yield, spec.volatility

    disc_r = math.exp(-r * t)
    disc_q = math.exp(-q * t)
    root_t = math.sqrt(t)
    pdf_d1 = float(norm.pdf(d1))

    # Shared by both option types.
    gamma = disc_q * pdf_d1 / (s * vol * root_t)
    vega = s * disc_q * pdf_d1 * root_t
    time_decay = -(s * disc_q * pdf_d1 * vol) / (2.0 * root_t)

    if spec.option_type is OptionType.CALL:
        delta = disc_q * float(norm.cdf(d1))
        theta = (
            time_decay + q * s * disc_q * float(norm.cdf(d1)) - r * k * disc_r * float(norm.cdf(d2))
        )
        rho = k * t * disc_r * float(norm.cdf(d2))
    else:
        delta = -disc_q * float(norm.cdf(-d1))
        theta = (
            time_decay
            - q * s * disc_q * float(norm.cdf(-d1))
            + r * k * disc_r * float(norm.cdf(-d2))
        )
        rho = -k * t * disc_r * float(norm.cdf(-d2))

    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def price_with_greeks(spec: OptionSpec) -> PricingResult:
    """Price and Greeks in the shape the API returns."""
    started = time.perf_counter()
    value = price(spec)
    sensitivities = greeks(spec)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    d1, d2 = _d1_d2(spec)
    return PricingResult(
        model=Model.BLACK_SCHOLES,
        price=value,
        greeks=sensitivities,
        compute_ms=elapsed_ms,
        diagnostics={"d1": d1, "d2": d2, "closed_form": True},
    )


def implied_volatility(
    spec: OptionSpec,
    market_price: float,
    *,
    lower: float = _IV_LOWER,
    upper: float = _IV_UPPER,
) -> float:
    """Back out the volatility that reproduces ``market_price``.

    Uses Brent's method on a bracket rather than Newton-Raphson: vega collapses for
    deep in- or out-of-the-money options, which makes Newton unstable exactly where
    users are most likely to probe. Brent is slower per iteration and much harder to
    break.

    The ``volatility`` field of ``spec`` is ignored; every other field is used.
    """
    _guard_european(spec)
    if market_price <= 0.0:
        raise ConvergenceError(f"market_price must be positive, got {market_price}")

    def objective(vol: float) -> float:
        return price(spec.bumped(volatility=vol)) - market_price

    lo, hi = objective(lower), objective(upper)
    if lo * hi > 0.0:
        # Both ends of the bracket sit on the same side of zero, so no root exists in
        # it. Almost always means the quoted price violates the no-arbitrage bounds.
        raise ConvergenceError(
            f"No implied volatility in [{lower}, {upper}] reproduces a price of "
            f"{market_price}. The quote may violate the no-arbitrage bounds for this "
            f"contract."
        )

    return float(brentq(objective, lower, upper, xtol=1e-10, maxiter=200))
