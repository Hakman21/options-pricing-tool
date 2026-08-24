"""Liveness, readiness and build metadata.

Liveness and readiness are separate on purpose. ``/health`` answers "is this process
alive" and must never touch a dependency, or a slow upstream will get the container
killed and restarted in a loop. ``/ready`` answers "should traffic be routed here"
and is allowed to check the things a request would actually use.
"""

from __future__ import annotations

from fastapi import APIRouter

from option_pricing import __version__ as library_version
from option_pricing.types import Model

from ..deps import MarketDataDep, SettingsDep
from ..schemas import HealthResponse, MetaResponse, ModelInfo, ReadyResponse

router = APIRouter(tags=["health"])

_MODEL_CATALOGUE = [
    ModelInfo(
        id=Model.BLACK_SCHOLES,
        name="Black-Scholes-Merton",
        description=(
            "Closed-form solution with continuous dividend yield. Exact and instant; "
            "the reference every other model is measured against."
        ),
        supports_american=False,
        stochastic=False,
    ),
    ModelInfo(
        id=Model.BINOMIAL,
        name="Binomial lattice (Cox-Ross-Rubinstein)",
        description=(
            "Vectorised backward induction over a recombining tree. Handles American "
            "exercise, and supplies delta, gamma and theta directly from the lattice."
        ),
        supports_american=True,
        stochastic=False,
    ),
    ModelInfo(
        id=Model.MONTE_CARLO,
        name="Monte Carlo (GBM)",
        description=(
            "Terminal-value simulation with antithetic and control variates. Reports a "
            "standard error and confidence interval alongside the price."
        ),
        supports_american=False,
        stochastic=True,
    ),
]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    """Cheap enough to call every few seconds. Touches nothing."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse, summary="Readiness probe")
def ready(market: MarketDataDep) -> ReadyResponse:
    """Confirms the pricing library imports and the cache is addressable."""
    if not market.is_enabled():
        market_status = "disabled by configuration"
    elif not market.client_available():
        # Reported rather than hidden: without this, a deployment built without the
        # `market` extra looks healthy right up until a user types a ticker.
        market_status = "unavailable (client not installed)"
    else:
        market_status = "ok"

    checks = {
        "pricing_library": f"ok ({library_version})",
        "market_data": market_status,
        "cache": f"ok ({market.cached_symbols()} symbols)",
    }
    return ReadyResponse(status="ready", checks=checks)


@router.get("/api/v1/meta", response_model=MetaResponse, summary="Build and model metadata")
def meta(settings: SettingsDep) -> MetaResponse:
    """What this build is and what it can do. Useful for debugging a deployment."""
    return MetaResponse(
        app_name=settings.app_name,
        version=settings.version,
        git_sha=settings.git_sha,
        build_time=settings.build_time,
        market_data_enabled=settings.market_data_enabled,
        models=_MODEL_CATALOGUE,
    )
