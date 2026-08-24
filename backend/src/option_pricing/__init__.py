"""Option pricing models.

A dependency-free (beyond NumPy and SciPy) library for pricing European and American
vanilla options three ways, with risk sensitivities and convergence diagnostics.

Nothing in this package imports a web framework. It is designed to be usable from a
notebook, a script, or a service, and to be tested without starting a server.

    >>> from option_pricing import OptionSpec, OptionType, black_scholes
    >>> spec = OptionSpec(
    ...     spot=100.0, strike=100.0, time_to_expiry=1.0,
    ...     risk_free_rate=0.05, volatility=0.2, option_type=OptionType.CALL,
    ... )
    >>> round(black_scholes.price(spec), 4)
    10.4506
"""

from __future__ import annotations

from . import binomial, black_scholes, convergence, greeks, monte_carlo
from .errors import (
    ConvergenceError,
    InvalidParameterError,
    LatticeStabilityError,
    PricingError,
    UnsupportedFeatureError,
)
from .types import Exercise, Greeks, Model, OptionSpec, OptionType, PricingResult

__version__ = "1.0.0"

# Grouped by kind rather than sorted alphabetically: the reading order (modules,
# then types, then errors) is more useful here than lexicographic order.
__all__ = [  # noqa: RUF022
    "__version__",
    # modules
    "black_scholes",
    "binomial",
    "monte_carlo",
    "convergence",
    "greeks",
    # types
    "OptionSpec",
    "OptionType",
    "Exercise",
    "Model",
    "Greeks",
    "PricingResult",
    # errors
    "PricingError",
    "InvalidParameterError",
    "UnsupportedFeatureError",
    "LatticeStabilityError",
    "ConvergenceError",
]
