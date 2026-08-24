"""Application factory and error translation.

The only interesting thing in here is the exception handling. The pricing library
raises typed errors; this module maps each one onto an HTTP status and a consistent
response body. That mapping is the whole reason the library is allowed to raise
rather than return sentinels - an ``UnsupportedFeatureError`` becomes a 422 that says
which constraint was violated, and the UI can show that text directly to the user.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from option_pricing.errors import (
    ConvergenceError,
    InvalidParameterError,
    LatticeStabilityError,
    PricingError,
    UnsupportedFeatureError,
)

from .routers import health, market, pricing
from .schemas import ErrorResponse
from .settings import get_settings

DESCRIPTION = """
Price European and American vanilla options three ways and compare the results.

* **Black-Scholes-Merton** - closed form with continuous dividend yield. Exact, and
  the reference the other two are measured against.
* **Binomial lattice (CRR)** - vectorised backward induction. Handles American
  exercise; supplies delta, gamma and theta straight from the tree.
* **Monte Carlo** - terminal-value simulation with antithetic and control variates,
  reported with a standard error and 95% confidence interval.

Every model returns all five Greeks. `/api/v1/convergence` shows the two numerical
models approaching the closed form, which is the clearest demonstration that they
are implemented correctly.
"""

# Errors that mean "the request was well-formed but cannot be satisfied as asked".
# 422 rather than 400: the syntax was fine, the semantics were not. Spelled as a
# literal because Starlette has renamed this constant across versions.
HTTP_422_UNPROCESSABLE = 422
HTTP_500_INTERNAL = 500

_UNPROCESSABLE: tuple[type[PricingError], ...] = (
    InvalidParameterError,
    UnsupportedFeatureError,
    LatticeStabilityError,
    ConvergenceError,
)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=DESCRIPTION,
        # Under /api so a single dev-server proxy rule covers the whole API
        # surface, docs included. /health and /ready stay at the root because they
        # are for whatever is supervising the process, not for the browser.
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        contact={"name": "Hakim Ahmed", "url": "https://hakimahmed.com"},
        license_info={"name": "MIT"},
    )

    # Normally empty, and that is the point: the Vite dev server proxies /api to
    # this process, so the browser sees one origin and no CORS headers are needed.
    # Set OPT_CORS_ORIGINS only if you ever call this API from a page served
    # somewhere else.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(PricingError)
    async def pricing_error_handler(_: Request, exc: PricingError) -> JSONResponse:
        unprocessable = isinstance(exc, _UNPROCESSABLE)
        code = HTTP_422_UNPROCESSABLE if unprocessable else HTTP_500_INTERNAL
        return JSONResponse(
            status_code=code,
            content=ErrorResponse(
                error=type(exc).__name__,
                detail=str(exc) if unprocessable else "Internal pricing error.",
            ).model_dump(),
        )

    app.include_router(health.router)
    app.include_router(pricing.router)
    app.include_router(market.router)

    return app


app = create_app()
