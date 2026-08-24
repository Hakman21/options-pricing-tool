"""Typed errors for the pricing library.

The library raises these rather than returning sentinel values or NaN, so the API
adapter can map each one onto a meaningful HTTP status without inspecting strings.
"""

from __future__ import annotations


class PricingError(Exception):
    """Base class for every error raised by :mod:`option_pricing`."""


class InvalidParameterError(PricingError):
    """A contract parameter is outside the domain the models are defined on."""


class UnsupportedFeatureError(PricingError):
    """The requested model cannot price the requested contract correctly.

    Raised, for example, when American exercise is requested from the Black-Scholes
    closed form. Returning a European price for an American contract would be a
    silently wrong answer, which is worse than a refusal.
    """


class LatticeStabilityError(PricingError):
    """The binomial lattice parameters admit arbitrage.

    Occurs when the risk-neutral probability ``p`` falls outside ``(0, 1)``, which
    means the time step is too large for the given volatility. Pricing on such a
    lattice produces numbers, but they are meaningless.
    """


class ConvergenceError(PricingError):
    """An iterative solver failed to converge within its bracket or iteration budget."""
