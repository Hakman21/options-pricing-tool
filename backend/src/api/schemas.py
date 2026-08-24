"""Request and response models.

This is the only place in the backend where the wire format is described. The
constraints here mirror the ones inside :class:`option_pricing.OptionSpec`
deliberately: Pydantic rejects malformed input at the edge with a structured 422 the
UI can render field by field, and the library re-checks its own invariants so it
stays safe when used without the API.

The same schema is also the source of truth for the frontend's TypeScript types,
which are generated from the OpenAPI document in CI. A change here that breaks the
client fails the build rather than production.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from option_pricing.types import (
    MAX_PRICE,
    MAX_RATE,
    MAX_VOL,
    MAX_YEARS,
    MIN_RATE,
    Exercise,
    Greeks,
    Model,
    OptionSpec,
    OptionType,
    PricingResult,
)

GreekName = Literal["delta", "gamma", "vega", "theta", "rho"]


class OptionInput(BaseModel):
    """A contract plus the market state needed to price it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "spot": 100.0,
                    "strike": 100.0,
                    "time_to_expiry": 1.0,
                    "risk_free_rate": 0.05,
                    "volatility": 0.2,
                    "dividend_yield": 0.0,
                    "option_type": "call",
                    "exercise": "european",
                }
            ]
        }
    )

    spot: float = Field(gt=0, le=MAX_PRICE, description="Current price of the underlying")
    strike: float = Field(gt=0, le=MAX_PRICE, description="Exercise price")
    time_to_expiry: float = Field(
        gt=0, le=MAX_YEARS, description="Years until expiry (0.25 = three months)"
    )
    risk_free_rate: float = Field(
        ge=MIN_RATE, le=MAX_RATE, description="Continuously compounded annual rate, 0.05 = 5%"
    )
    volatility: float = Field(gt=0, le=MAX_VOL, description="Annualised volatility, 0.2 = 20%")
    dividend_yield: float = Field(
        default=0.0, ge=0, le=MAX_RATE, description="Continuous dividend yield"
    )
    option_type: OptionType = OptionType.CALL
    exercise: Exercise = Exercise.EUROPEAN

    def to_spec(self) -> OptionSpec:
        return OptionSpec(
            spot=self.spot,
            strike=self.strike,
            time_to_expiry=self.time_to_expiry,
            risk_free_rate=self.risk_free_rate,
            volatility=self.volatility,
            dividend_yield=self.dividend_yield,
            option_type=self.option_type,
            exercise=self.exercise,
        )


class ModelParams(BaseModel):
    """Numerical settings. Ignored by the closed form, which has none."""

    steps: int = Field(default=500, ge=3, le=5000, description="Binomial lattice steps")
    paths: int = Field(
        default=100_000, ge=1_000, le=2_000_000, description="Monte Carlo sample paths"
    )
    seed: int = Field(default=42, ge=0, description="RNG seed; results are reproducible")
    antithetic: bool = Field(default=True, description="Pair each draw Z with -Z")
    control_variate: bool = Field(
        default=True, description="Regress the payoff on the discounted terminal price"
    )


class GreeksOut(BaseModel):
    """Raw derivatives. Vega and rho are per 1.00 absolute move; theta is per year."""

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    @classmethod
    def of(cls, greeks: Greeks) -> GreeksOut:
        return cls(**greeks.as_dict())


class PricingResultOut(BaseModel):
    model: Model
    price: float
    greeks: GreeksOut
    compute_ms: float
    standard_error: float | None = None
    confidence_interval: tuple[float, float] | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def of(cls, result: PricingResult) -> PricingResultOut:
        return cls(
            model=result.model,
            price=result.price,
            greeks=GreeksOut.of(result.greeks),
            compute_ms=result.compute_ms,
            standard_error=result.standard_error,
            confidence_interval=result.confidence_interval,
            diagnostics=result.diagnostics,
        )


# ── /price ────────────────────────────────────────────────────────────────────


class PriceRequest(BaseModel):
    option: OptionInput
    model: Model = Model.BLACK_SCHOLES
    params: ModelParams = Field(default_factory=ModelParams)


# ── /compare ──────────────────────────────────────────────────────────────────


class ComparisonRow(PricingResultOut):
    """One model's result, measured against the reference price."""

    abs_error: float = Field(description="Signed difference from the reference price")
    rel_error: float = Field(description="abs_error as a fraction of the reference price")


class UnsupportedModel(BaseModel):
    """A model that cannot price this contract, and why.

    Returned alongside the results rather than as an error: asking three models to
    price an American option is a reasonable request, and two of them declining is
    information, not a failure.
    """

    model: Model
    reason: str


class CompareRequest(BaseModel):
    option: OptionInput
    params: ModelParams = Field(default_factory=ModelParams)


class CompareResponse(BaseModel):
    reference_model: Model
    reference_price: float
    results: list[ComparisonRow]
    unsupported: list[UnsupportedModel] = Field(default_factory=list)


# ── /convergence ──────────────────────────────────────────────────────────────


class BinomialPoint(BaseModel):
    steps: int
    price: float
    error: float


class MonteCarloPoint(BaseModel):
    paths: int
    price: float
    standard_error: float
    ci_low: float
    ci_high: float
    error: float


class ConvergenceRequest(BaseModel):
    option: OptionInput
    max_steps: int = Field(default=200, ge=10, le=400)
    max_paths: int = Field(default=200_000, ge=1_000, le=200_000)
    seed: int = Field(default=42, ge=0)


class ConvergenceResponse(BaseModel):
    reference_price: float
    reference_model: Model
    binomial: list[BinomialPoint]
    monte_carlo: list[MonteCarloPoint]


# ── /payoff, /sensitivity, /paths ─────────────────────────────────────────────


class PayoffRequest(BaseModel):
    option: OptionInput
    points: int = Field(default=121, ge=11, le=501)
    span: float = Field(
        default=0.6, gt=0, le=2.0, description="Grid half-width as a fraction of strike"
    )


class PayoffResponse(BaseModel):
    spots: list[float]
    payoffs: list[float]
    profits: list[float]
    breakeven: float
    premium: float
    strike: float
    current_spot: float


class SensitivityRequest(BaseModel):
    option: OptionInput
    greek: GreekName = "delta"
    model: Model = Model.BLACK_SCHOLES
    points: int = Field(default=81, ge=11, le=201)
    span: float = Field(default=0.5, gt=0, le=2.0)
    steps: int = Field(default=200, ge=3, le=1000)


class SensitivityResponse(BaseModel):
    greek: GreekName
    model: Model
    spots: list[float]
    values: list[float]
    current_spot: float
    strike: float


class PathsRequest(BaseModel):
    option: OptionInput
    n_paths: int = Field(default=100, ge=1, le=500)
    n_steps: int = Field(default=100, ge=1, le=1000)
    seed: int = Field(default=42, ge=0)


class PathsResponse(BaseModel):
    times: list[float]
    paths: list[list[float]]
    strike: float
    terminal_mean: float


# ── /implied-vol ──────────────────────────────────────────────────────────────


class ImpliedVolRequest(BaseModel):
    option: OptionInput = Field(description="volatility is ignored; every other field is used")
    market_price: float = Field(gt=0, le=MAX_PRICE)


class ImpliedVolResponse(BaseModel):
    implied_volatility: float
    market_price: float
    reprice_check: float = Field(description="Closed-form price at the solved volatility")


# ── market data ───────────────────────────────────────────────────────────────


class MarketQuote(BaseModel):
    symbol: str
    spot: float
    currency: str
    realised_vol_30d: float | None
    as_of: str
    cache_hit: bool
    source: str


# ── meta ──────────────────────────────────────────────────────────────────────


class ModelInfo(BaseModel):
    id: Model
    name: str
    description: str
    supports_american: bool
    stochastic: bool


class MetaResponse(BaseModel):
    app_name: str
    version: str
    git_sha: str
    build_time: str
    market_data_enabled: bool
    models: list[ModelInfo]


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]


class ErrorResponse(BaseModel):
    """The shape every handled failure takes, so the UI has one thing to parse."""

    error: str = Field(description="Machine-readable error class, e.g. UnsupportedFeatureError")
    detail: str = Field(description="Human-readable explanation, safe to display")
