"""Pricing endpoints.

Every route here is a thin translation layer: parse, call the pricing library, shape
the result. There is no financial logic in this file, which is the point - the maths
is tested without a web server, and this module is tested without doing any maths.
"""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter

from option_pricing import binomial, black_scholes, convergence, monte_carlo
from option_pricing.errors import UnsupportedFeatureError
from option_pricing.types import Model, PricingResult

from ..deps import SettingsDep
from ..schemas import (
    BinomialPoint,
    CompareRequest,
    CompareResponse,
    ComparisonRow,
    ConvergenceRequest,
    ConvergenceResponse,
    ImpliedVolRequest,
    ImpliedVolResponse,
    ModelParams,
    MonteCarloPoint,
    PathsRequest,
    PathsResponse,
    PayoffRequest,
    PayoffResponse,
    PriceRequest,
    PricingResultOut,
    SensitivityRequest,
    SensitivityResponse,
    UnsupportedModel,
)

router = APIRouter(prefix="/api/v1", tags=["pricing"])


def _dispatch(model: Model, spec: object, params: ModelParams) -> PricingResult:
    """Route to the right pricer with the parameters that model actually uses."""
    if model is Model.BLACK_SCHOLES:
        return black_scholes.price_with_greeks(spec)  # type: ignore[arg-type]
    if model is Model.BINOMIAL:
        return binomial.price_with_greeks(spec, steps=params.steps)  # type: ignore[arg-type]
    return monte_carlo.price_with_greeks(
        spec,  # type: ignore[arg-type]
        paths=params.paths,
        seed=params.seed,
        antithetic=params.antithetic,
        control_variate=params.control_variate,
    )


@router.post("/price", response_model=PricingResultOut, summary="Price with one model")
def price(request: PriceRequest) -> PricingResultOut:
    """Price a contract with a single model, returning all five Greeks.

    Requesting American exercise from Black-Scholes or Monte Carlo returns 422 naming
    the constraint. Returning a European price for an American contract would be
    silently wrong, which is worse than a refusal.
    """
    spec = request.option.to_spec()
    return PricingResultOut.of(_dispatch(request.model, spec, request.params))


@router.post("/compare", response_model=CompareResponse, summary="Price with every model")
def compare(request: CompareRequest) -> CompareResponse:
    """Run all three models on identical inputs and measure them against a reference.

    For a European contract the reference is the closed form. For an American one
    there is no closed form, so a high-resolution lattice stands in and the other two
    models report why they declined rather than failing the whole request.
    """
    spec = request.option.to_spec()

    if spec.is_american:
        reference_model = Model.BINOMIAL
        reference_price = binomial.price(spec, steps=min(4000, request.params.steps * 4))
        candidates = [Model.BINOMIAL]
    else:
        reference_model = Model.BLACK_SCHOLES
        reference_price = black_scholes.price(spec)
        candidates = [Model.BLACK_SCHOLES, Model.BINOMIAL, Model.MONTE_CARLO]

    rows: list[ComparisonRow] = []
    unsupported: list[UnsupportedModel] = []

    for model in (Model.BLACK_SCHOLES, Model.BINOMIAL, Model.MONTE_CARLO):
        if model not in candidates:
            reason = {
                Model.BLACK_SCHOLES: (
                    "The closed form cannot capture the early-exercise premium of an "
                    "American contract."
                ),
                Model.MONTE_CARLO: (
                    "Valuing American exercise by simulation needs a regression method "
                    "such as Longstaff-Schwartz, which is not implemented."
                ),
            }.get(model, "Not applicable to this contract.")
            unsupported.append(UnsupportedModel(model=model, reason=reason))
            continue

        try:
            result = _dispatch(model, spec, request.params)
        except UnsupportedFeatureError as exc:
            unsupported.append(UnsupportedModel(model=model, reason=str(exc)))
            continue

        abs_error = result.price - reference_price
        rows.append(
            ComparisonRow(
                **PricingResultOut.of(result).model_dump(),
                abs_error=abs_error,
                rel_error=abs_error / reference_price if reference_price else 0.0,
            )
        )

    return CompareResponse(
        reference_model=reference_model,
        reference_price=reference_price,
        results=rows,
        unsupported=unsupported,
    )


@router.post("/convergence", response_model=ConvergenceResponse, summary="Convergence sweeps")
def convergence_sweep(request: ConvergenceRequest, settings: SettingsDep) -> ConvergenceResponse:
    """Both numerical models plotted against the exact answer as resolution increases.

    The two signatures are visibly different: the lattice oscillates around the true
    price with decaying amplitude, while simulation converges stochastically with its
    confidence band narrowing as 1/sqrt(n).
    """
    spec = request.option.to_spec()

    max_steps = min(request.max_steps, settings.max_convergence_steps)
    max_paths = min(request.max_paths, settings.max_convergence_paths)

    reference, binomial_points = convergence.binomial_convergence(
        spec, convergence.default_step_grid(max_steps)
    )

    mc_points: list[MonteCarloPoint] = []
    if not spec.is_american:
        _, raw = convergence.monte_carlo_convergence(
            spec, convergence.default_path_grid(max_paths), seed=request.seed
        )
        mc_points = [
            MonteCarloPoint(
                paths=p.paths,
                price=p.price,
                standard_error=p.standard_error,
                ci_low=p.ci_low,
                ci_high=p.ci_high,
                error=p.error,
            )
            for p in raw
        ]

    return ConvergenceResponse(
        reference_price=reference,
        reference_model=Model.BINOMIAL if spec.is_american else Model.BLACK_SCHOLES,
        binomial=[
            BinomialPoint(steps=p.steps, price=p.price, error=p.error) for p in binomial_points
        ],
        monte_carlo=mc_points,
    )


@router.post("/payoff", response_model=PayoffResponse, summary="Payoff and profit curve")
def payoff(request: PayoffRequest) -> PayoffResponse:
    """Payoff at expiry and profit after the premium, across a grid of spot prices."""
    spec = request.option.to_spec()
    premium = binomial.price(spec, steps=500) if spec.is_american else black_scholes.price(spec)
    spots, payoffs, profits, breakeven = convergence.payoff_curve(
        spec, points=request.points, span=request.span, premium=premium
    )
    return PayoffResponse(
        spots=spots,
        payoffs=payoffs,
        profits=profits,
        breakeven=breakeven,
        premium=premium,
        strike=spec.strike,
        current_spot=spec.spot,
    )


@router.post(
    "/sensitivity", response_model=SensitivityResponse, summary="A Greek plotted against spot"
)
def sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    """One Greek across a spot grid, everything else held fixed."""
    spec = request.option.to_spec()
    model = Model.BINOMIAL if spec.is_american else request.model
    spots, values = convergence.sensitivity_curve(
        spec,
        request.greek,
        model=model,
        points=request.points,
        span=request.span,
        steps=request.steps,
    )
    return SensitivityResponse(
        greek=request.greek,
        model=model,
        spots=spots,
        values=values,
        current_spot=spec.spot,
        strike=spec.strike,
    )


@router.post("/paths", response_model=PathsResponse, summary="Sample GBM trajectories")
def paths(request: PathsRequest) -> PathsResponse:
    """A handful of simulated price paths, purely to illustrate what Monte Carlo does.

    Deliberately separate from pricing: never simulate a million trajectories to draw
    a hundred lines.
    """
    spec = request.option.to_spec()
    matrix = monte_carlo.simulate_paths(
        spec, n_paths=request.n_paths, n_steps=request.n_steps, seed=request.seed
    )
    times = np.linspace(0.0, spec.time_to_expiry, request.n_steps + 1).tolist()
    return PathsResponse(
        times=times,
        paths=matrix.tolist(),
        strike=spec.strike,
        terminal_mean=float(matrix[:, -1].mean()),
    )


@router.post(
    "/implied-vol", response_model=ImpliedVolResponse, summary="Solve for implied volatility"
)
def implied_vol(request: ImpliedVolRequest) -> ImpliedVolResponse:
    """Back out the volatility that reproduces an observed market price.

    Brent's method on a bracket rather than Newton-Raphson: vega collapses deep in
    and out of the money, which is exactly where Newton becomes unstable.
    """
    spec = request.option.to_spec()
    solved = black_scholes.implied_volatility(spec, request.market_price)
    return ImpliedVolResponse(
        implied_volatility=solved,
        market_price=request.market_price,
        reprice_check=black_scholes.price(spec.bumped(volatility=solved)),
    )
