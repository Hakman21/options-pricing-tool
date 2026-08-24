"""Convergence sweeps and curve generation for the comparison views.

This module is what turns three numbers into something worth looking at. The
binomial lattice and Monte Carlo both approach the closed-form price, but they get
there in visibly different ways:

- the **lattice** oscillates around the true value with decaying amplitude, because
  as the step count changes the strike moves relative to the terminal nodes;
- **simulation** converges stochastically, its confidence band narrowing as 1/√n.

Plotting both against the exact answer is the clearest possible demonstration that
the numerical models are correct, and it is far more informative than a table.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import binomial, black_scholes, monte_carlo
from .types import Model, OptionSpec

__all__ = [
    "BinomialConvergencePoint",
    "MonteCarloConvergencePoint",
    "binomial_convergence",
    "default_path_grid",
    "default_step_grid",
    "monte_carlo_convergence",
    "payoff_curve",
    "sensitivity_curve",
]


@dataclass(frozen=True, slots=True)
class BinomialConvergencePoint:
    steps: int
    price: float
    error: float  # signed, against the closed form


@dataclass(frozen=True, slots=True)
class MonteCarloConvergencePoint:
    paths: int
    price: float
    standard_error: float
    ci_low: float
    ci_high: float
    error: float


def default_step_grid(max_steps: int = 300) -> list[int]:
    """Consecutive small step counts, where the oscillation is actually visible.

    A log-spaced grid would hide the effect: the alternation happens between
    *adjacent* step counts, so the grid has to be dense at the low end.
    """
    dense = list(range(3, min(max_steps, 60) + 1))
    if max_steps <= 60:
        return dense
    sparse = list(range(70, max_steps + 1, 10))
    return dense + sparse


def default_path_grid(max_paths: int = 200_000) -> list[int]:
    """Roughly log-spaced path counts, since the error falls as 1/√n."""
    grid = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000, 500_000]
    return [n for n in grid if n <= max_paths]


def binomial_convergence(
    spec: OptionSpec, steps_grid: list[int] | None = None
) -> tuple[float, list[BinomialConvergencePoint]]:
    """Lattice price at each step count, with the closed form as the reference.

    For an American contract there is no closed form to compare against, so the
    reference is the lattice's own price at a high step count.
    """
    grid = steps_grid or default_step_grid()

    if spec.is_american:
        reference = binomial.price(spec, steps=max(grid) * 4)
    else:
        reference = black_scholes.price(spec)

    points = [
        BinomialConvergencePoint(
            steps=n, price=(p := binomial.price(spec, steps=n)), error=p - reference
        )
        for n in grid
    ]
    return reference, points


def monte_carlo_convergence(
    spec: OptionSpec,
    paths_grid: list[int] | None = None,
    *,
    seed: int = monte_carlo.DEFAULT_SEED,
) -> tuple[float, list[MonteCarloConvergencePoint]]:
    """Simulated price and 95% band at each path count.

    Each point uses a different seed derived from the base one. Reusing a single seed
    would make the sequence look far smoother than simulation really is, because
    every estimate would share the same draws.
    """
    grid = paths_grid or default_path_grid()
    reference = black_scholes.price(spec)

    points: list[MonteCarloConvergencePoint] = []
    for index, n in enumerate(grid):
        result = monte_carlo.price_with_greeks(spec, paths=n, seed=seed + index * 977)
        low, high = result.confidence_interval or (result.price, result.price)
        points.append(
            MonteCarloConvergencePoint(
                paths=n,
                price=result.price,
                standard_error=result.standard_error or 0.0,
                ci_low=low,
                ci_high=high,
                error=result.price - reference,
            )
        )
    return reference, points


def payoff_curve(
    spec: OptionSpec,
    *,
    points: int = 121,
    span: float = 0.6,
    premium: float | None = None,
) -> tuple[list[float], list[float], list[float], float]:
    """Payoff at expiry and profit/loss across a spot grid.

    Returns ``(spots, payoffs, profits, breakeven)``. The premium defaults to the
    closed-form price, so the profit curve is the payoff shifted down by what the
    option actually costs.
    """
    cost = black_scholes.price(spec) if premium is None else premium
    low = spec.strike * (1.0 - span)
    high = spec.strike * (1.0 + span)
    spots = np.linspace(low, high, points)

    sign = spec.option_type.sign
    payoffs = np.maximum(sign * (spots - spec.strike), 0.0)
    profits = payoffs - cost
    breakeven = spec.strike + sign * cost

    return spots.tolist(), payoffs.tolist(), profits.tolist(), float(breakeven)


def sensitivity_curve(
    spec: OptionSpec,
    greek: str,
    *,
    model: Model = Model.BLACK_SCHOLES,
    points: int = 81,
    span: float = 0.5,
    steps: int = 200,
) -> tuple[list[float], list[float]]:
    """A single Greek plotted against spot, holding everything else fixed.

    Watching gamma spike at the strike as expiry approaches teaches more about
    convexity than any amount of prose.
    """
    valid = {"delta", "gamma", "vega", "theta", "rho"}
    if greek not in valid:
        raise ValueError(f"greek must be one of {sorted(valid)}, got {greek!r}")

    low = spec.strike * (1.0 - span)
    high = spec.strike * (1.0 + span)
    spots = np.linspace(low, high, points)

    values: list[float] = []
    for s in spots:
        bumped = spec.bumped(spot=float(s))
        if model is Model.BINOMIAL:
            result = binomial.price_with_greeks(bumped, steps=steps)
        else:
            result = black_scholes.price_with_greeks(bumped)
        values.append(getattr(result.greeks, greek))

    return spots.tolist(), values
