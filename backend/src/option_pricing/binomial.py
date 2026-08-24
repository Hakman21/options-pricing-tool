"""Cox-Ross-Rubinstein binomial lattice.

Two implementation choices are worth calling out.

**The backward induction is vectorised.** Each time level is one NumPy array that
shrinks by a single element per step, so there is no Python loop over nodes. At
``steps=2000`` that is the difference between roughly 200 ms and half a minute.

**Delta, gamma and theta are read off the lattice, not bumped.** The tree already
contains the option value at spots above and below the current one (levels 1 and 2),
so three of the five Greeks cost nothing beyond a single extra pricing pass. Only
vega and rho require re-pricing, because volatility and the rate change the lattice
geometry itself.

American exercise costs one ``np.maximum`` per level, which is why it is supported
here and refused by the other two models.
"""

from __future__ import annotations

import math
import time

import numpy as np

from .errors import InvalidParameterError, LatticeStabilityError
from .types import Greeks, Model, OptionSpec, PricingResult

__all__ = ["DEFAULT_STEPS", "MAX_STEPS", "price", "price_with_greeks"]

DEFAULT_STEPS = 500
MAX_STEPS = 5000

# ``math.exp`` overflows a float64 just above 709. The extreme node of a CRR lattice
# sits at ``S * exp(sigma * sqrt(T * steps))``, so this bounds the exponent before
# it can produce an inf that silently propagates into an infinite option price.
_MAX_LOG_SPAN = 700.0

# Bump sizes for the two Greeks the lattice cannot supply directly.
#
# The volatility bump is deliberately large. Changing sigma changes u and d, which
# changes where the strike sits relative to the lattice nodes, so a tiny bump
# measures discretisation noise rather than vega. One vol point averages over it.
_VEGA_BUMP = 1e-2
# Changing r moves only the risk-neutral probability, leaving the node geometry
# alone, so rho is smooth in the bump and a small step is safe.
_RHO_BUMP = 1e-4


def _validate_steps(steps: int) -> None:
    if steps < 3:
        raise InvalidParameterError(
            f"steps must be at least 3 to read gamma off the lattice, got {steps}"
        )
    if steps > MAX_STEPS:
        raise InvalidParameterError(f"steps must be at most {MAX_STEPS}, got {steps}")


def _lattice(
    spec: OptionSpec, steps: int
) -> tuple[float, dict[int, tuple[np.ndarray, np.ndarray]], dict[str, float]]:
    """Run the backward induction, capturing the levels the Greeks need.

    Returns the value at the root, a mapping of ``level -> (values, spots)`` for
    levels 1 and 2, and the lattice parameters for diagnostics.
    """
    s0, k = spec.spot, spec.strike
    t, r, q, vol = spec.time_to_expiry, spec.risk_free_rate, spec.dividend_yield, spec.volatility
    sign = float(spec.option_type.sign)

    dt = t / steps
    log_u = vol * math.sqrt(dt)

    if log_u * steps > _MAX_LOG_SPAN:
        raise LatticeStabilityError(
            f"volatility {vol} over {t} years with {steps} steps spans "
            f"{log_u * steps:.0f} log units, which overflows double precision. "
            f"Reduce the step count or the volatility."
        )

    u = math.exp(log_u)
    d = 1.0 / u
    disc = math.exp(-r * dt)
    growth = math.exp((r - q) * dt)
    p = (growth - d) / (u - d)

    if not 0.0 < p < 1.0:
        raise LatticeStabilityError(
            f"risk-neutral probability p={p:.6f} is outside (0, 1): this lattice "
            f"admits arbitrage. The time step is too large for a volatility of "
            f"{vol} - increase the step count."
        )

    def node_spots(level: int) -> np.ndarray:
        # A node at ``level`` with ``j`` up-moves sits at S * u^j * d^(level-j),
        # which collapses to S * u^(2j - level) because d = 1/u.
        exponents = 2 * np.arange(level + 1) - level
        return s0 * np.power(u, exponents)

    def intrinsic(spots: np.ndarray) -> np.ndarray:
        return np.maximum(sign * (spots - k), 0.0)

    values = intrinsic(node_spots(steps))
    captured: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    for level in range(steps - 1, -1, -1):
        values = disc * (p * values[1:] + (1.0 - p) * values[:-1])
        spots = node_spots(level) if (spec.is_american or level <= 2) else None
        if spec.is_american:
            assert spots is not None
            values = np.maximum(values, intrinsic(spots))
        if level in (1, 2):
            assert spots is not None
            captured[level] = (values.copy(), spots)

    params = {"dt": dt, "u": u, "d": d, "p": p, "discount": disc}
    return float(values[0]), captured, params


def price(spec: OptionSpec, steps: int = DEFAULT_STEPS) -> float:
    """Lattice price of a European or American option."""
    _validate_steps(steps)
    value, _, _ = _lattice(spec, steps)
    return value


def price_with_greeks(spec: OptionSpec, steps: int = DEFAULT_STEPS) -> PricingResult:
    """Price plus all five Greeks.

    Delta, gamma and theta come straight from the lattice; vega and rho are central
    differences over two extra lattice builds each.
    """
    _validate_steps(steps)
    started = time.perf_counter()

    value, captured, params = _lattice(spec, steps)

    (v1, s1) = captured[1]
    (v2, s2) = captured[2]

    # Level 1 holds one down-node and one up-node either side of the root.
    delta = float((v1[1] - v1[0]) / (s1[1] - s1[0]))

    # Level 2 holds three nodes: the outer two give two local deltas, and the change
    # between them over the spot distance they span is gamma.
    delta_up = (v2[2] - v2[1]) / (s2[2] - s2[1])
    delta_down = (v2[1] - v2[0]) / (s2[1] - s2[0])
    gamma = float((delta_up - delta_down) / (0.5 * (s2[2] - s2[0])))

    # The middle node at level 2 sits at (very nearly) today's spot, two time steps
    # into the future, so the change from the root is a clean time derivative.
    theta = float((v2[1] - value) / (2.0 * params["dt"]))

    vega = float(
        (
            _lattice(spec.bumped(volatility=spec.volatility + _VEGA_BUMP), steps)[0]
            - _lattice(spec.bumped(volatility=spec.volatility - _VEGA_BUMP), steps)[0]
        )
        / (2.0 * _VEGA_BUMP)
    )
    rho = float(
        (
            _lattice(spec.bumped(risk_free_rate=spec.risk_free_rate + _RHO_BUMP), steps)[0]
            - _lattice(spec.bumped(risk_free_rate=spec.risk_free_rate - _RHO_BUMP), steps)[0]
        )
        / (2.0 * _RHO_BUMP)
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return PricingResult(
        model=Model.BINOMIAL,
        price=value,
        greeks=Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho),
        compute_ms=elapsed_ms,
        diagnostics={
            "steps": steps,
            "up_factor": params["u"],
            "down_factor": params["d"],
            "risk_neutral_prob": params["p"],
            "dt": params["dt"],
            "exercise": spec.exercise.value,
        },
    )
