"""Tier 1: golden values.

Every expected number here comes from a published worked example, cited in the test.
These catch the class of bug that everything else masks - a sign error, a misplaced
square root, ``d2`` where ``d1`` belongs - because they compare against an answer
computed by someone else.
"""

from __future__ import annotations

import math

import pytest

from option_pricing import OptionSpec, OptionType
from option_pricing import black_scholes as bs
from option_pricing.errors import ConvergenceError, UnsupportedFeatureError
from option_pricing.types import Exercise


class TestGoldenValues:
    def test_hull_chapter_15_european_call(self) -> None:
        """Hull, *Options, Futures and Other Derivatives*, ch. 15: c = 4.76."""
        spec = OptionSpec(
            spot=42.0, strike=40.0, time_to_expiry=0.5, risk_free_rate=0.10, volatility=0.20
        )
        assert bs.price(spec) == pytest.approx(4.759422, abs=1e-6)

    def test_hull_chapter_15_european_put(self) -> None:
        """Same contract as a put: p = 0.81."""
        spec = OptionSpec(
            spot=42.0,
            strike=40.0,
            time_to_expiry=0.5,
            risk_free_rate=0.10,
            volatility=0.20,
            option_type=OptionType.PUT,
        )
        assert bs.price(spec) == pytest.approx(0.808599, abs=1e-6)

    def test_canonical_atm_call(self, atm_call: OptionSpec) -> None:
        """S=K=100, r=5%, sigma=20%, T=1 is the most widely quoted example there is."""
        assert bs.price(atm_call) == pytest.approx(10.450584, abs=1e-6)

    def test_canonical_atm_put(self, atm_put: OptionSpec) -> None:
        assert bs.price(atm_put) == pytest.approx(5.573526, abs=1e-6)

    def test_dividend_yield_reduces_call_value(self, atm_call: OptionSpec) -> None:
        """A dividend-paying underlying is worth less to a call holder."""
        with_dividend = bs.price(atm_call.bumped(dividend_yield=0.03))
        assert with_dividend < bs.price(atm_call)
        assert with_dividend == pytest.approx(8.652529, abs=1e-6)


class TestAnalyticGreeks:
    def test_atm_call_greeks(self, atm_call: OptionSpec) -> None:
        g = bs.greeks(atm_call)
        assert g.delta == pytest.approx(0.636831, abs=1e-6)
        assert g.gamma == pytest.approx(0.018762, abs=1e-6)
        assert g.vega == pytest.approx(37.524035, abs=1e-6)
        assert g.theta == pytest.approx(-6.414028, abs=1e-6)
        assert g.rho == pytest.approx(53.232482, abs=1e-6)

    def test_call_and_put_delta_differ_by_the_discounted_dividend_factor(self) -> None:
        """delta_call - delta_put = e^(-qT), an identity that follows from parity."""
        spec = OptionSpec(
            spot=95.0,
            strike=100.0,
            time_to_expiry=0.75,
            risk_free_rate=0.03,
            volatility=0.35,
            dividend_yield=0.02,
        )
        call_delta = bs.greeks(spec).delta
        put_delta = bs.greeks(spec.bumped(option_type=OptionType.PUT)).delta
        expected = math.exp(-spec.dividend_yield * spec.time_to_expiry)
        assert call_delta - put_delta == pytest.approx(expected, abs=1e-12)

    def test_gamma_and_vega_are_type_independent(self) -> None:
        """A call and a put on the same contract share gamma and vega exactly."""
        spec = OptionSpec(
            spot=88.0, strike=100.0, time_to_expiry=1.5, risk_free_rate=0.04, volatility=0.28
        )
        call, put = bs.greeks(spec), bs.greeks(spec.bumped(option_type=OptionType.PUT))
        assert call.gamma == pytest.approx(put.gamma, rel=1e-12)
        assert call.vega == pytest.approx(put.vega, rel=1e-12)


class TestImpliedVolatility:
    @pytest.mark.parametrize("true_vol", [0.05, 0.15, 0.20, 0.45, 1.20])
    def test_round_trip(self, atm_call: OptionSpec, true_vol: float) -> None:
        """Pricing at a known vol and solving back must return that vol."""
        spec = atm_call.bumped(volatility=true_vol)
        recovered = bs.implied_volatility(spec, bs.price(spec))
        assert recovered == pytest.approx(true_vol, abs=1e-8)

    def test_round_trip_far_out_of_the_money(self) -> None:
        """Where vega is small, which is exactly where Newton-Raphson would struggle."""
        spec = OptionSpec(
            spot=100.0, strike=250.0, time_to_expiry=0.25, risk_free_rate=0.05, volatility=0.6
        )
        assert bs.implied_volatility(spec, bs.price(spec)) == pytest.approx(0.6, abs=1e-6)

    def test_arbitrage_violating_price_is_rejected(self, atm_call: OptionSpec) -> None:
        """A call cannot be worth more than the underlying, so no vol reproduces it."""
        with pytest.raises(ConvergenceError, match="no-arbitrage"):
            bs.implied_volatility(atm_call, atm_call.spot * 1.5)

    def test_non_positive_market_price_is_rejected(self, atm_call: OptionSpec) -> None:
        with pytest.raises(ConvergenceError, match="must be positive"):
            bs.implied_volatility(atm_call, 0.0)


class TestRefusals:
    def test_american_exercise_is_refused_not_approximated(self, atm_call: OptionSpec) -> None:
        """Returning a European price for an American contract would be silently wrong."""
        american = atm_call.bumped(exercise=Exercise.AMERICAN)
        with pytest.raises(UnsupportedFeatureError, match="binomial"):
            bs.price(american)
        with pytest.raises(UnsupportedFeatureError):
            bs.greeks(american)
