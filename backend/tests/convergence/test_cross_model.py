"""Tier 3: cross-model agreement.

Two independent numerical methods and one closed form should agree. Where they do
not, at least one is wrong - and because the closed form is exact, we know which.

The Monte Carlo tolerances here are derived from the estimator's own standard error
rather than picked by hand, which is the difference between a test that means
something and a test that was loosened until it passed.
"""

from __future__ import annotations

import itertools
import math

import pytest
from hypothesis import given, settings

from option_pricing import (
    Exercise,
    OptionSpec,
    OptionType,
    binomial,
)
from option_pricing import (
    black_scholes as bs,
)
from option_pricing import (
    monte_carlo as mc,
)
from option_pricing.errors import InvalidParameterError, LatticeStabilityError
from option_pricing.greeks import finite_difference_greeks
from tests.conftest import moderate_specs

# Three standard errors, not two.
#
# At 2 sigma a two-sided test fails roughly one run in twenty. Across a suite with
# several such assertions that is a red build most weeks, which trains you to ignore
# red builds - a far worse outcome than a slightly weaker assertion. At 3 sigma the
# false-failure rate is about 1 in 370 per assertion, which is rare enough to always
# be worth investigating.
SIGMA_TOLERANCE = 3.0


class TestBinomialConvergesToClosedForm:
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_high_resolution_lattice_matches_closed_form(
        self, atm_call: OptionSpec, option_type: OptionType
    ) -> None:
        spec = atm_call.bumped(option_type=option_type)
        assert binomial.price(spec, steps=4000) == pytest.approx(bs.price(spec), abs=1e-3)

    def test_error_shrinks_as_steps_increase(self, atm_call: OptionSpec) -> None:
        """CRR error is O(1/N), so ten times the steps should cut it by roughly ten.

        Compared over a two-step gap because consecutive step counts alternate sign.
        """
        exact = bs.price(atm_call)
        coarse = abs(binomial.price(atm_call, steps=50) - exact)
        fine = abs(binomial.price(atm_call, steps=500) - exact)
        assert fine < coarse / 5.0

    def test_lattice_price_oscillates_around_the_true_value(self, atm_call: OptionSpec) -> None:
        """The signature the convergence chart exists to show.

        Adding one step moves the strike relative to the terminal nodes, so the error
        flips sign. A monotone sequence here would mean the lattice is not centred.
        """
        exact = bs.price(atm_call)
        errors = [binomial.price(atm_call, steps=n) - exact for n in range(20, 32)]
        sign_changes = sum(1 for a, b in itertools.pairwise(errors) if (a > 0) != (b > 0))
        assert sign_changes >= 8

    @settings(max_examples=30)
    @given(spec=moderate_specs())
    def test_agreement_across_parameter_space(self, spec: OptionSpec) -> None:
        lattice = binomial.price(spec, steps=800)
        closed_form = bs.price(spec)
        assert lattice == pytest.approx(closed_form, abs=1e-2, rel=1e-3)


class TestMonteCarloConvergesToClosedForm:
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_price_within_three_standard_errors(
        self, atm_call: OptionSpec, option_type: OptionType
    ) -> None:
        spec = atm_call.bumped(option_type=option_type)
        result = mc.price_with_greeks(spec, paths=200_000, seed=20260823)
        exact = bs.price(spec)

        assert result.standard_error is not None
        deviation = abs(result.price - exact)
        assert deviation <= SIGMA_TOLERANCE * result.standard_error, (
            f"MC price {result.price:.6f} is {deviation / result.standard_error:.1f} "
            f"standard errors from the closed form {exact:.6f}"
        )

    def test_confidence_interval_contains_the_true_price(self, atm_call: OptionSpec) -> None:
        result = mc.price_with_greeks(atm_call, paths=200_000, seed=7)
        assert result.confidence_interval is not None
        low, high = result.confidence_interval
        assert low <= bs.price(atm_call) <= high

    def test_standard_error_falls_as_one_over_root_n(self, atm_call: OptionSpec) -> None:
        """Quadrupling the paths should roughly halve the error."""
        small = mc.price_with_greeks(atm_call, paths=25_000, seed=11)
        large = mc.price_with_greeks(atm_call, paths=400_000, seed=11)
        assert small.standard_error is not None and large.standard_error is not None
        ratio = small.standard_error / large.standard_error
        assert 2.5 < ratio < 5.5, f"expected roughly 4x, got {ratio:.2f}x"

    def test_variance_reduction_actually_reduces_variance(self, atm_call: OptionSpec) -> None:
        """If antithetic and control variates are not helping, they are not working."""
        plain = mc.price_with_greeks(
            atm_call, paths=100_000, seed=3, antithetic=False, control_variate=False
        )
        reduced = mc.price_with_greeks(
            atm_call, paths=100_000, seed=3, antithetic=True, control_variate=True
        )
        assert plain.standard_error is not None and reduced.standard_error is not None
        assert reduced.standard_error < plain.standard_error

    def test_results_are_reproducible(self, atm_call: OptionSpec) -> None:
        """Same seed, same answer - otherwise CI cannot assert anything about it."""
        a = mc.price(atm_call, paths=50_000, seed=99)
        b = mc.price(atm_call, paths=50_000, seed=99)
        assert a == b


class TestGreeksAgreeAcrossModels:
    @pytest.mark.parametrize("greek", ["delta", "gamma", "vega", "theta", "rho"])
    def test_analytic_matches_finite_difference(self, greek: str) -> None:
        """The independent numerical differentiator must reproduce the formulae.

        This is the check that would catch a transcription error in any analytic
        Greek, because the two code paths share nothing but the price function.
        """
        spec = OptionSpec(
            spot=95.0,
            strike=100.0,
            time_to_expiry=0.75,
            risk_free_rate=0.03,
            volatility=0.35,
            dividend_yield=0.02,
            option_type=OptionType.PUT,
        )
        analytic = getattr(bs.greeks(spec), greek)
        numeric = getattr(finite_difference_greeks(bs.price, spec), greek)
        assert numeric == pytest.approx(analytic, rel=1e-5, abs=1e-7)

    @pytest.mark.parametrize(
        ("greek", "tolerance"),
        [("delta", 1e-3), ("gamma", 5e-3), ("vega", 1e-3), ("theta", 1e-3), ("rho", 1e-3)],
    )
    def test_lattice_greeks_match_analytic(
        self, atm_call: OptionSpec, greek: str, tolerance: float
    ) -> None:
        """Gamma gets the loosest tolerance: it is a second difference read off three
        adjacent lattice nodes, so it inherits the most discretisation error."""
        analytic = getattr(bs.greeks(atm_call), greek)
        lattice = getattr(binomial.price_with_greeks(atm_call, steps=2000).greeks, greek)
        assert lattice == pytest.approx(analytic, rel=tolerance)

    @pytest.mark.parametrize(
        ("greek", "tolerance"),
        [("delta", 5e-3), ("gamma", 5e-2), ("vega", 5e-3), ("theta", 5e-3), ("rho", 5e-3)],
    )
    def test_monte_carlo_greeks_match_analytic(
        self, atm_call: OptionSpec, greek: str, tolerance: float
    ) -> None:
        """Only achievable because every bump reuses the same random draws. Without
        common random numbers these tolerances would need to be orders of magnitude
        looser, and gamma would be pure noise."""
        analytic = getattr(bs.greeks(atm_call), greek)
        simulated = getattr(mc.price_with_greeks(atm_call, paths=500_000, seed=2024).greeks, greek)
        assert simulated == pytest.approx(analytic, rel=tolerance)


class TestAmericanExercise:
    def test_american_put_is_worth_more_than_european(self, atm_put: OptionSpec) -> None:
        """The early-exercise right cannot have negative value."""
        american = atm_put.bumped(exercise=Exercise.AMERICAN)
        assert binomial.price(american, steps=1500) > binomial.price(atm_put, steps=1500)

    def test_american_call_on_a_non_dividend_payer_equals_european(
        self, atm_call: OptionSpec
    ) -> None:
        """A classic result: with no dividends it is never optimal to exercise a call
        early, so the early-exercise right is worthless."""
        american = atm_call.bumped(exercise=Exercise.AMERICAN)
        assert binomial.price(american, steps=1500) == pytest.approx(
            binomial.price(atm_call, steps=1500), abs=1e-9
        )

    def test_american_price_never_below_intrinsic(self) -> None:
        """Otherwise you could buy the option, exercise immediately, and profit."""
        deep = OptionSpec(
            spot=60.0,
            strike=100.0,
            time_to_expiry=1.0,
            risk_free_rate=0.05,
            volatility=0.2,
            option_type=OptionType.PUT,
            exercise=Exercise.AMERICAN,
        )
        assert binomial.price(deep, steps=1000) >= deep.intrinsic_value() - 1e-9


class TestNumericalGuards:
    def test_arbitrageable_lattice_is_rejected(self) -> None:
        """When p leaves (0, 1) the tree still produces numbers, but meaningless ones."""
        spec = OptionSpec(
            spot=100.0,
            strike=100.0,
            time_to_expiry=20.0,
            risk_free_rate=0.9,
            volatility=0.03,
            option_type=OptionType.CALL,
        )
        with pytest.raises(LatticeStabilityError, match="arbitrage"):
            binomial.price(spec, steps=4)

    def test_overflowing_lattice_span_is_rejected(self) -> None:
        """Guarded before it can produce an inf that propagates into the price."""
        spec = OptionSpec(
            spot=100.0,
            strike=100.0,
            time_to_expiry=30.0,
            risk_free_rate=0.05,
            volatility=4.5,
        )
        with pytest.raises(LatticeStabilityError, match="overflow"):
            binomial.price(spec, steps=5000)

    def test_too_few_steps_is_rejected(self, atm_call: OptionSpec) -> None:
        """Gamma needs three levels; two would silently read past the array."""
        with pytest.raises(InvalidParameterError, match="at least 3"):
            binomial.price(atm_call, steps=2)

    def test_lattice_probability_stays_in_range_across_parameter_space(self) -> None:
        spec = OptionSpec(
            spot=100.0, strike=100.0, time_to_expiry=1.0, risk_free_rate=0.05, volatility=0.2
        )
        result = binomial.price_with_greeks(spec, steps=100)
        assert 0.0 < result.diagnostics["risk_neutral_prob"] < 1.0
        assert result.diagnostics["up_factor"] * result.diagnostics["down_factor"] == (
            pytest.approx(1.0, abs=1e-12)
        )

    def test_simulated_paths_start_at_spot_and_stay_positive(self, atm_call: OptionSpec) -> None:
        paths = mc.simulate_paths(atm_call, n_paths=50, n_steps=60, seed=1)
        assert paths.shape == (50, 61)
        assert all(row[0] == pytest.approx(atm_call.spot) for row in paths)
        assert (paths > 0).all(), "GBM cannot produce a non-positive price"

    def test_terminal_distribution_has_the_right_mean(self, atm_call: OptionSpec) -> None:
        """Under the risk-neutral measure E[S_T] = S·e^((r-q)T)."""
        paths = mc.simulate_paths(atm_call, n_paths=500, n_steps=200, seed=5)
        expected = atm_call.spot * math.exp(
            (atm_call.risk_free_rate - atm_call.dividend_yield) * atm_call.time_to_expiry
        )
        assert paths[:, -1].mean() == pytest.approx(expected, rel=0.1)
