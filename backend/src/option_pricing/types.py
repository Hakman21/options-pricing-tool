"""Core value types shared by every pricing model.

These are plain dataclasses with no Pydantic and no framework imports: the pricing
library must stay usable from a notebook, a script, or another package without
dragging in a web stack.

Conventions used throughout the library
---------------------------------------
- Time is measured in **years**.
- Rates and yields are **continuously compounded decimals** (0.05 is 5%).
- ``vega`` is the derivative with respect to a **1.00 absolute change** in
  volatility (i.e. 100 vol points), not the per-point figure traders quote.
- ``theta`` is the derivative with respect to **calendar time in years**, so it is
  normally negative. Divide by 365 for the per-day figure.
- ``rho`` is the derivative with respect to a 1.00 absolute change in the rate.

Sticking to raw derivatives and scaling only at the presentation layer keeps the
finite-difference cross-checks in the test suite honest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from .errors import InvalidParameterError

# Domain limits. These are deliberately generous but finite: they exist so that a
# malformed request fails loudly at the boundary instead of producing an overflow
# or a silent NaN deep inside a lattice.
MAX_PRICE = 1e7
MAX_YEARS = 30.0
MAX_VOL = 5.0
MIN_RATE = -0.05
MAX_RATE = 1.0


class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"

    @property
    def sign(self) -> int:
        """+1 for a call, -1 for a put. Lets one formula serve both."""
        return 1 if self is OptionType.CALL else -1


class Exercise(StrEnum):
    EUROPEAN = "european"
    AMERICAN = "american"


class Model(StrEnum):
    BLACK_SCHOLES = "black_scholes"
    BINOMIAL = "binomial"
    MONTE_CARLO = "monte_carlo"


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """An option contract plus the market state needed to price it.

    Frozen so a spec can be shared between models without any of them mutating it,
    and so bumped copies (used for finite-difference Greeks) are always explicit.
    """

    spot: float
    strike: float
    time_to_expiry: float
    risk_free_rate: float
    volatility: float
    dividend_yield: float = 0.0
    option_type: OptionType = OptionType.CALL
    exercise: Exercise = Exercise.EUROPEAN

    def __post_init__(self) -> None:
        self._check("spot", self.spot, low=0.0, high=MAX_PRICE, strict_low=True)
        self._check("strike", self.strike, low=0.0, high=MAX_PRICE, strict_low=True)
        self._check("time_to_expiry", self.time_to_expiry, low=0.0, high=MAX_YEARS, strict_low=True)
        self._check("volatility", self.volatility, low=0.0, high=MAX_VOL, strict_low=True)
        self._check("risk_free_rate", self.risk_free_rate, low=MIN_RATE, high=MAX_RATE)
        self._check("dividend_yield", self.dividend_yield, low=0.0, high=MAX_RATE)

    @staticmethod
    def _check(
        name: str, value: float, *, low: float, high: float, strict_low: bool = False
    ) -> None:
        if not math.isfinite(value):
            raise InvalidParameterError(f"{name} must be a finite number, got {value!r}")
        too_low = value <= low if strict_low else value < low
        if too_low:
            bound = "greater than" if strict_low else "at least"
            raise InvalidParameterError(f"{name} must be {bound} {low}, got {value}")
        if value > high:
            raise InvalidParameterError(f"{name} must be at most {high}, got {value}")

    # -- convenience -----------------------------------------------------------

    @property
    def is_call(self) -> bool:
        return self.option_type is OptionType.CALL

    @property
    def is_american(self) -> bool:
        return self.exercise is Exercise.AMERICAN

    @property
    def moneyness(self) -> float:
        """Forward moneyness ``S/K``. Above 1.0 a call is in the money."""
        return self.spot / self.strike

    def bumped(self, **changes: Any) -> OptionSpec:
        """Return a copy with fields replaced. Used by finite-difference Greeks."""
        return replace(self, **changes)

    def intrinsic_value(self, spot: float | None = None) -> float:
        s = self.spot if spot is None else spot
        return max(self.option_type.sign * (s - self.strike), 0.0)


@dataclass(frozen=True, slots=True)
class Greeks:
    """First and second order risk sensitivities.

    Every model populates all five. Where a model has no closed form for one, it is
    produced by finite difference, and the test suite asserts the two approaches
    agree with the analytic values within stated tolerances.
    """

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    def as_dict(self) -> dict[str, float]:
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
            "rho": self.rho,
        }


@dataclass(frozen=True, slots=True)
class PricingResult:
    """What every model returns.

    ``standard_error`` and ``confidence_interval`` are populated only by simulation
    models. A Monte Carlo price quoted without its error is not a result, it is a
    guess with extra decimal places.
    """

    model: Model
    price: float
    greeks: Greeks
    compute_ms: float
    standard_error: float | None = None
    confidence_interval: tuple[float, float] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
