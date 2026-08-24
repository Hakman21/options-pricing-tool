"""Tier 2: property-based tests.

Instead of asserting that specific inputs give specific outputs, these assert
relationships that must hold for *every* input, and let Hypothesis hunt for the ones
that break them. When a property fails, Hypothesis shrinks the counterexample to the
smallest one that still fails, which usually points straight at the bug.

The properties chosen here are financial rather than numerical. Put-call parity is a
no-arbitrage identity: if it holds across thousands of randomly generated contracts,
the pricing core is almost certainly correct. That is a far stronger statement than
any number of hand-picked examples.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from option_pricing import OptionSpec, OptionType
from option_pricing import black_scholes as bs
from tests.conftest import european_specs, moderate_specs


class TestNoArbitrage:
    @given(spec=european_specs())
    def test_put_call_parity(self, spec: OptionSpec) -> None:
        """C - P = S·e^(-qT) - K·e^(-rT), exactly, for every European contract.

        This single property subsumes an enormous number of possible bugs: any error
        in d1, d2, the discounting, or the dividend adjustment breaks it.
        """
        call = bs.price(spec.bumped(option_type=OptionType.CALL))
        put = bs.price(spec.bumped(option_type=OptionType.PUT))

        forward = spec.spot * math.exp(-spec.dividend_yield * spec.time_to_expiry)
        discounted_strike = spec.strike * math.exp(-spec.risk_free_rate * spec.time_to_expiry)

        assert call - put == pytest.approx(forward - discounted_strike, abs=1e-8, rel=1e-10)

    @given(spec=european_specs())
    def test_price_within_no_arbitrage_bounds(self, spec: OptionSpec) -> None:
        """A call is worth at least its discounted intrinsic and never more than the
        (dividend-adjusted) underlying. Violating either implies a free lunch."""
        forward = spec.spot * math.exp(-spec.dividend_yield * spec.time_to_expiry)
        discounted_strike = spec.strike * math.exp(-spec.risk_free_rate * spec.time_to_expiry)

        call = bs.price(spec.bumped(option_type=OptionType.CALL))
        assert call >= max(forward - discounted_strike, 0.0) - 1e-9
        assert call <= forward + 1e-9

        put = bs.price(spec.bumped(option_type=OptionType.PUT))
        assert put >= max(discounted_strike - forward, 0.0) - 1e-9
        assert put <= discounted_strike + 1e-9

    @given(spec=european_specs())
    def test_price_is_never_negative(self, spec: OptionSpec) -> None:
        assert bs.price(spec) >= 0.0


class TestMonotonicity:
    @given(spec=moderate_specs(), bump=st.floats(0.01, 0.5))
    def test_call_increases_and_put_decreases_in_spot(self, spec: OptionSpec, bump: float) -> None:
        """A call gains from a higher underlying; a put loses. Non-strict, because
        deep out of the money both are numerically zero."""
        higher = spec.bumped(spot=spec.spot * (1.0 + bump))
        assert (
            bs.price(higher.bumped(option_type=OptionType.CALL))
            >= bs.price(spec.bumped(option_type=OptionType.CALL)) - 1e-12
        )
        assert (
            bs.price(higher.bumped(option_type=OptionType.PUT))
            <= bs.price(spec.bumped(option_type=OptionType.PUT)) + 1e-12
        )

    @given(spec=moderate_specs(), bump=st.floats(0.01, 0.5))
    def test_both_types_increase_in_volatility(self, spec: OptionSpec, bump: float) -> None:
        """Optionality is long volatility regardless of direction - this is why vega
        is positive for calls and puts alike."""
        noisier = spec.bumped(volatility=spec.volatility + bump)
        assert bs.price(noisier) >= bs.price(spec) - 1e-12

    @given(spec=moderate_specs())
    def test_call_decreases_in_strike(self, spec: OptionSpec) -> None:
        """The right to buy at a higher price is worth less."""
        call = spec.bumped(option_type=OptionType.CALL)
        assert bs.price(call.bumped(strike=call.strike * 1.1)) <= bs.price(call) + 1e-12


class TestGreekProperties:
    @given(spec=european_specs())
    def test_delta_lies_in_its_theoretical_range(self, spec: OptionSpec) -> None:
        """Call delta in (0, e^-qT], put delta in [-e^-qT, 0). A delta outside this
        would imply a hedge ratio that cannot exist."""
        cap = math.exp(-spec.dividend_yield * spec.time_to_expiry)
        call_delta = bs.greeks(spec.bumped(option_type=OptionType.CALL)).delta
        put_delta = bs.greeks(spec.bumped(option_type=OptionType.PUT)).delta

        assert 0.0 <= call_delta <= cap + 1e-12
        assert -cap - 1e-12 <= put_delta <= 0.0

    @given(spec=european_specs())
    def test_gamma_and_vega_are_non_negative(self, spec: OptionSpec) -> None:
        """Both follow from the option payoff being convex in the underlying."""
        g = bs.greeks(spec)
        assert g.gamma >= 0.0
        assert g.vega >= 0.0

    @given(spec=european_specs())
    def test_rho_sign_follows_option_type(self, spec: OptionSpec) -> None:
        """Higher rates discount the strike more: good for a call, bad for a put."""
        assert bs.greeks(spec.bumped(option_type=OptionType.CALL)).rho >= 0.0
        assert bs.greeks(spec.bumped(option_type=OptionType.PUT)).rho <= 0.0

    @given(spec=moderate_specs())
    def test_gamma_peaks_near_the_money(self, spec: OptionSpec) -> None:
        """Convexity is concentrated where the payoff kinks.

        Both spots are constructed rather than filtered: an ``assume`` on moneyness
        would discard most of what the strategy generates, which Hypothesis rightly
        flags as distorting the input distribution.
        """
        at_the_money = spec.bumped(spot=spec.strike)
        far_away = spec.bumped(spot=spec.strike * 3.0)
        assert bs.greeks(at_the_money).gamma >= bs.greeks(far_away).gamma


class TestImpliedVolatilityRoundTrip:
    @given(spec=moderate_specs())
    def test_solver_recovers_any_volatility(self, spec: OptionSpec) -> None:
        """Price at sigma, solve back, get sigma.

        Restricted to contracts with meaningful vega, and that restriction is the
        interesting part. Implied volatility is only *identifiable* where the price
        actually responds to volatility. A deep in-the-money option days from expiry
        is worth its intrinsic value to within double precision - vega there can be
        of order 1e-12, so a whole range of volatilities reproduces the same price
        and no solver, however good, can distinguish between them.

        That is a property of the problem, not a defect in the implementation, and
        the UI reflects it by declining to quote an implied vol when vega is
        negligible.
        """
        price = bs.price(spec)
        assume(price > 1e-6)
        assume(bs.greeks(spec).vega > 1e-4)
        assert bs.implied_volatility(spec, price) == pytest.approx(
            spec.volatility, abs=1e-5, rel=1e-5
        )
