"""Monte Carlo simulation under geometric Brownian motion.

For a vanilla European option the payoff depends only on the terminal price, so we
sample ``S_T`` directly from its lognormal distribution rather than stepping paths
forward. That is the correct approach, not a shortcut: path stepping would add
discretisation error to the sampling error we already have, for no benefit. (Paths
are still simulated separately, but only to draw the illustration in the UI.)

Three details make this a credible implementation rather than a demonstration:

**Antithetic variates.** Every draw ``Z`` is paired with ``-Z``. The pair average is
an unbiased estimator with lower variance, and - importantly - the standard error is
computed *across pairs*, because the two halves are not independent. Treating all
``n`` samples as independent would understate the error by roughly √2.

**A control variate.** The discounted terminal price is a random variable whose mean
we know exactly (``S·e^(-qT)``) and which correlates strongly with the payoff.
Regressing the payoff on it removes most of the remaining variance.

**Common random numbers for the Greeks.** Every bumped revaluation reuses the same
underlying draws. Without this, the difference between two independently simulated
prices is dominated by simulation noise rather than by the sensitivity being
measured - the single most common mistake in Monte Carlo Greeks.
"""

from __future__ import annotations

import math
import time

import numpy as np

from .errors import InvalidParameterError, UnsupportedFeatureError
from .types import Greeks, Model, OptionSpec, PricingResult

__all__ = ["DEFAULT_PATHS", "MAX_PATHS", "price", "price_with_greeks", "simulate_paths"]

DEFAULT_PATHS = 100_000
MAX_PATHS = 2_000_000
DEFAULT_SEED = 42

# 95% two-sided normal quantile, used for the reported confidence interval.
_Z95 = 1.959963984540054

# Bump sizes, as fractions of spot or absolute rate/vol moves. Delta and gamma bumps
# are relative to spot so they behave the same for a £5 stock and a £5,000 index.
# Gamma's is deliberately wider: a second difference divides by h squared, so it
# amplifies whatever noise survives the common random numbers.
_DELTA_BUMP_REL = 1e-2
_GAMMA_BUMP_REL = 5e-2
_VEGA_BUMP = 1e-2
_RHO_BUMP = 1e-3


def _guard_european(spec: OptionSpec) -> None:
    if spec.is_american:
        raise UnsupportedFeatureError(
            "This Monte Carlo engine prices European exercise only. Valuing an "
            "American option by simulation requires a regression-based method such "
            "as Longstaff-Schwartz; use the binomial model instead."
        )


def _validate_paths(paths: int) -> None:
    if paths < 1000:
        raise InvalidParameterError(f"paths must be at least 1000, got {paths}")
    if paths > MAX_PATHS:
        raise InvalidParameterError(f"paths must be at most {MAX_PATHS}, got {paths}")


def _draws(paths: int, antithetic: bool, seed: int) -> tuple[np.ndarray, int]:
    """Generate the standard normal draws, returning them and the pair count.

    With antithetics the array is ``[Z, -Z]``, so sample ``i`` and sample ``i + half``
    form a pair. A pair count of zero means the samples are independent.
    """
    rng = np.random.default_rng(seed)
    if antithetic:
        half = paths // 2
        z = rng.standard_normal(half)
        return np.concatenate([z, -z]), half
    return rng.standard_normal(paths), 0


def _run(
    *,
    spot: float,
    strike: float,
    years: float,
    rate: float,
    yield_: float,
    vol: float,
    sign: float,
    z: np.ndarray,
    n_pairs: int,
    control_variate: bool,
) -> tuple[float, float]:
    """Core estimator. Returns ``(price, standard_error)``.

    Takes loose scalars rather than an :class:`OptionSpec` so that bumped
    revaluations skip re-validation and can push ``years`` slightly below its normal
    domain without tripping the contract checks.
    """
    drift = (rate - yield_ - 0.5 * vol * vol) * years
    diffusion = vol * math.sqrt(years)
    terminal = spot * np.exp(drift + diffusion * z)

    discount = math.exp(-rate * years)
    samples = discount * np.maximum(sign * (terminal - strike), 0.0)

    if control_variate:
        # E[e^(-rT) S_T] = S e^(-qT) exactly, under the risk-neutral measure.
        control = discount * terminal
        expected_control = spot * math.exp(-yield_ * years)
        centred = control - control.mean()
        variance = float(np.mean(centred * centred))
        if variance > 0.0:
            # Estimating beta from the same sample introduces an O(1/n) bias. It is
            # far smaller than the variance it removes, and vanishes as n grows.
            beta = float(np.mean(centred * (samples - samples.mean()))) / variance
            samples = samples - beta * (control - expected_control)

    effective = 0.5 * (samples[:n_pairs] + samples[n_pairs:]) if n_pairs else samples

    mean = float(effective.mean())
    standard_error = float(effective.std(ddof=1) / math.sqrt(effective.size))
    return mean, standard_error


def price(
    spec: OptionSpec,
    paths: int = DEFAULT_PATHS,
    *,
    seed: int = DEFAULT_SEED,
    antithetic: bool = True,
    control_variate: bool = True,
) -> float:
    """Simulated price. Use :func:`price_with_greeks` to also get the error estimate."""
    _guard_european(spec)
    _validate_paths(paths)
    z, n_pairs = _draws(paths, antithetic, seed)
    value, _ = _run(
        spot=spec.spot,
        strike=spec.strike,
        years=spec.time_to_expiry,
        rate=spec.risk_free_rate,
        yield_=spec.dividend_yield,
        vol=spec.volatility,
        sign=float(spec.option_type.sign),
        z=z,
        n_pairs=n_pairs,
        control_variate=control_variate,
    )
    return value


def price_with_greeks(
    spec: OptionSpec,
    paths: int = DEFAULT_PATHS,
    *,
    seed: int = DEFAULT_SEED,
    antithetic: bool = True,
    control_variate: bool = True,
) -> PricingResult:
    """Simulated price, standard error, confidence interval and bumped Greeks."""
    _guard_european(spec)
    _validate_paths(paths)
    started = time.perf_counter()

    z, n_pairs = _draws(paths, antithetic, seed)
    sign = float(spec.option_type.sign)

    base = {
        "strike": spec.strike,
        "rate": spec.risk_free_rate,
        "yield_": spec.dividend_yield,
        "vol": spec.volatility,
        "sign": sign,
        "z": z,
        "n_pairs": n_pairs,
        "control_variate": control_variate,
    }

    def evaluate(**overrides: float) -> float:
        args = {**base, "spot": spec.spot, "years": spec.time_to_expiry, **overrides}
        return _run(**args)[0]  # type: ignore[arg-type]

    value, standard_error = _run(spot=spec.spot, years=spec.time_to_expiry, **base)  # type: ignore[arg-type]

    h_s = spec.spot * _DELTA_BUMP_REL
    delta = (evaluate(spot=spec.spot + h_s) - evaluate(spot=spec.spot - h_s)) / (2.0 * h_s)

    h_g = spec.spot * _GAMMA_BUMP_REL
    gamma = (evaluate(spot=spec.spot + h_g) - 2.0 * value + evaluate(spot=spec.spot - h_g)) / (
        h_g * h_g
    )

    vega = (
        evaluate(vol=spec.volatility + _VEGA_BUMP) - evaluate(vol=spec.volatility - _VEGA_BUMP)
    ) / (2.0 * _VEGA_BUMP)

    rho = (
        evaluate(rate=spec.risk_free_rate + _RHO_BUMP)
        - evaluate(rate=spec.risk_free_rate - _RHO_BUMP)
    ) / (2.0 * _RHO_BUMP)

    # theta is the derivative with respect to calendar time, which is minus the
    # derivative with respect to remaining life.
    h_t = min(1e-2, spec.time_to_expiry * 0.25)
    theta = -(
        evaluate(years=spec.time_to_expiry + h_t) - evaluate(years=spec.time_to_expiry - h_t)
    ) / (2.0 * h_t)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    half_width = _Z95 * standard_error

    return PricingResult(
        model=Model.MONTE_CARLO,
        price=value,
        greeks=Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho),
        compute_ms=elapsed_ms,
        standard_error=standard_error,
        confidence_interval=(value - half_width, value + half_width),
        diagnostics={
            "paths": paths,
            "effective_samples": n_pairs if n_pairs else paths,
            "antithetic": antithetic,
            "control_variate": control_variate,
            "seed": seed,
        },
    )


def simulate_paths(
    spec: OptionSpec,
    n_paths: int = 100,
    n_steps: int = 100,
    *,
    seed: int = DEFAULT_SEED,
) -> np.ndarray:
    """Full GBM trajectories, purely for the illustration in the UI.

    Shape ``(n_paths, n_steps + 1)``, starting at spot. Deliberately separate from the
    pricing path: never simulate a million trajectories to draw a hundred lines.
    """
    if not 1 <= n_paths <= 500:
        raise InvalidParameterError(f"n_paths must be between 1 and 500, got {n_paths}")
    if not 1 <= n_steps <= 1000:
        raise InvalidParameterError(f"n_steps must be between 1 and 1000, got {n_steps}")

    rng = np.random.default_rng(seed)
    dt = spec.time_to_expiry / n_steps
    drift = (spec.risk_free_rate - spec.dividend_yield - 0.5 * spec.volatility**2) * dt
    diffusion = spec.volatility * math.sqrt(dt)

    increments = drift + diffusion * rng.standard_normal((n_paths, n_steps))
    log_paths = np.concatenate([np.zeros((n_paths, 1)), np.cumsum(increments, axis=1)], axis=1)
    result: np.ndarray = spec.spot * np.exp(log_paths)
    return result
