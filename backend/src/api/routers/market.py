"""Live market data lookup.

One route, and most of its value is in what happens when it fails. Every upstream
problem becomes a 503 carrying a message the UI can show verbatim, and the frontend
falls back to manual entry rather than breaking.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from ..deps import MarketDataDep
from ..market_data import MarketDataUnavailableError
from ..schemas import MarketQuote

router = APIRouter(prefix="/api/v1/market", tags=["market data"])


@router.get(
    "/{symbol}",
    response_model=MarketQuote,
    summary="Spot price and realised volatility for a ticker",
    responses={503: {"description": "Upstream unavailable; enter values manually"}},
)
def quote(
    market: MarketDataDep,
    symbol: str = Path(min_length=1, max_length=16, examples=["AAPL", "^GSPC", "VOD.L"]),
) -> MarketQuote:
    """Fetch a quote, served from a 15-minute cache where possible.

    ``realised_vol_30d`` is the annualised standard deviation of the last 30 daily log
    returns, scaled by sqrt(252). It is a reasonable starting point for the volatility
    input, not a substitute for an implied vol, and the UI presents it as such.
    """
    try:
        result, cache_hit = market.get_quote(symbol)
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return MarketQuote(
        symbol=result.symbol,
        spot=result.spot,
        currency=result.currency,
        realised_vol_30d=result.realised_vol_30d,
        as_of=result.as_of,
        cache_hit=cache_hit,
        source=result.source,
    )
