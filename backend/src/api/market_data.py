"""Market data adapter.

Yahoo Finance has no official public API; ``yfinance`` scrapes an undocumented
endpoint that changes without notice and rate-limits aggressively. Treating it as
unreliable is not pessimism, it is the observed behaviour.

So the adapter is built to fail well:

- a short timeout, because a hanging upstream must not hang the pricing API;
- a TTL cache, so repeated lookups of the same symbol cost nothing and the upstream
  sees a fraction of the traffic;
- a single typed exception, which the API maps to 503 with an actionable message.

The UI catches that 503 and tells the user to enter values by hand, and every field
remains editable regardless. A demo that survives its data source going down is the
entire reason for putting a boundary here.

Note that ``MarketDataUnavailableError`` lives in this module, not in ``option_pricing``:
fetching quotes is an application concern, and the pricing library stays free of it.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import sys
from datetime import UTC, datetime
from typing import Any

from cachetools import TTLCache

from .settings import Settings

__all__ = ["MarketDataService", "MarketDataUnavailableError", "Quote"]


class MarketDataUnavailableError(RuntimeError):
    """Live market data could not be retrieved. Manual entry remains available."""


class Quote:
    """A point-in-time snapshot of a symbol."""

    __slots__ = ("as_of", "currency", "realised_vol_30d", "source", "spot", "symbol")

    def __init__(
        self,
        symbol: str,
        spot: float,
        currency: str,
        realised_vol_30d: float | None,
        as_of: str,
        source: str,
    ) -> None:
        self.symbol = symbol
        self.spot = spot
        self.currency = currency
        self.realised_vol_30d = realised_vol_30d
        self.as_of = as_of
        self.source = source


def _annualised_realised_vol(closes: list[float]) -> float | None:
    """Sample standard deviation of daily log returns, scaled to one year.

    Uses 252 trading days rather than 365 calendar days: volatility accumulates on
    days the market is open. Returns ``None`` rather than a misleading number when
    there is not enough history.
    """
    if len(closes) < 20:
        return None
    returns = [math.log(b / a) for a, b in itertools.pairwise(closes) if a > 0.0 and b > 0.0]
    if len(returns) < 19:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252.0)


class MarketDataService:
    """Cached, timeout-bounded access to live quotes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: TTLCache[str, Quote] = TTLCache(
            maxsize=settings.market_cache_size, ttl=settings.market_cache_ttl_s
        )

    def is_enabled(self) -> bool:
        """Is live lookup switched on in configuration?"""
        return self._settings.market_data_enabled

    @staticmethod
    def client_available() -> bool:
        """Is the optional client actually installed?

        Separate from :meth:`is_enabled` on purpose. "Configured on" and "able to
        work" are different states, and conflating them is how a deployment reports
        itself ready while the feature is dead - which is exactly what happened when
        the container was built without the ``market`` extra.
        """
        # sys.modules is checked first because find_spec is unreliable once a
        # module is already loaded: for a module stubbed out as None it raises
        # ValueError rather than answering the question.
        if "yfinance" in sys.modules:
            return sys.modules["yfinance"] is not None
        try:
            return importlib.util.find_spec("yfinance") is not None
        except (ImportError, ValueError):
            return False

    def cached_symbols(self) -> int:
        return len(self._cache)

    def get_quote(self, symbol: str) -> tuple[Quote, bool]:
        """Return ``(quote, cache_hit)``.

        Raises :class:`MarketDataUnavailableError` for every upstream failure mode, so
        callers never have to know what ``yfinance`` raises.
        """
        if not self._settings.market_data_enabled:
            raise MarketDataUnavailableError(
                "Live market data is disabled on this deployment. Enter the spot "
                "price and volatility manually."
            )

        key = symbol.strip().upper()
        if not key or len(key) > 16 or not all(c.isalnum() or c in ".-^=" for c in key):
            raise MarketDataUnavailableError(f"{symbol!r} is not a valid ticker symbol.")

        cached = self._cache.get(key)
        if cached is not None:
            return cached, True

        quote = self._fetch(key)
        self._cache[key] = quote
        return quote, False

    def _fetch(self, symbol: str) -> Quote:
        try:
            import yfinance  # imported lazily: the API must start without it
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise MarketDataUnavailableError(
                "The market data client is not installed on this deployment. Enter values manually."
            ) from exc

        try:
            ticker = yfinance.Ticker(symbol)
            history: Any = ticker.history(
                period="3mo", interval="1d", timeout=self._settings.market_data_timeout_s
            )
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"Could not reach the market data provider for {symbol}. Enter values "
                f"manually, or try again shortly."
            ) from exc

        if history is None or len(history) == 0:
            raise MarketDataUnavailableError(
                f"No price history returned for {symbol}. Check the ticker symbol."
            )

        closes = [float(c) for c in history["Close"].tolist() if c == c and c > 0]
        if not closes:
            raise MarketDataUnavailableError(f"No usable closing prices returned for {symbol}.")

        currency = "USD"
        try:
            info = ticker.fast_info
            currency = str(getattr(info, "currency", None) or "USD").upper()
        except Exception:
            pass

        return Quote(
            symbol=symbol,
            spot=closes[-1],
            currency=currency,
            realised_vol_30d=_annualised_realised_vol(closes[-31:]),
            as_of=datetime.now(UTC).isoformat(timespec="seconds"),
            source="yfinance",
        )
