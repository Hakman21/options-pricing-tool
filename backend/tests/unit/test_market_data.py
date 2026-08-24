"""Market data adapter: caching, validation, and every failure path.

The adapter's job is not really "fetch a price" - it is "fail in a way the rest of
the system can handle". These tests spend most of their effort on the failure modes,
because those are what actually reach users when an undocumented upstream endpoint
changes shape or starts rate-limiting.

A fake ``yfinance`` module is injected into ``sys.modules`` so none of this touches
the network, and the tests stay deterministic in CI.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from api.market_data import (
    MarketDataService,
    MarketDataUnavailableError,
    _annualised_realised_vol,
)
from api.settings import Settings


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "market_data_enabled": True,
        "market_cache_ttl_s": 900,
        "market_cache_size": 8,
    }
    return Settings(**{**base, **overrides})


class FakeHistory:
    """Minimal stand-in for the pandas frame yfinance returns."""

    def __init__(self, closes: list[float]) -> None:
        self._closes = closes

    def __len__(self) -> int:
        return len(self._closes)

    def __getitem__(self, key: str) -> Any:
        assert key == "Close"
        return SimpleNamespace(tolist=lambda: self._closes)


def install_fake_yfinance(
    monkeypatch: pytest.MonkeyPatch,
    closes: list[float] | None = None,
    *,
    raises: Exception | None = None,
    currency: str = "GBP",
) -> None:
    module = ModuleType("yfinance")

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            self.fast_info = SimpleNamespace(currency=currency)

        def history(self, **_: Any) -> FakeHistory:
            if raises is not None:
                raise raises
            return FakeHistory(closes or [])

    module.Ticker = FakeTicker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", module)


@pytest.fixture
def prices() -> list[float]:
    """A deterministic 90-day series with a mild upward drift."""
    return [100.0 * math.exp(0.0004 * i + 0.01 * math.sin(i)) for i in range(90)]


class TestRealisedVolatility:
    def test_returns_none_without_enough_history(self) -> None:
        """Better to say nothing than to quote a volatility from ten data points."""
        assert _annualised_realised_vol([100.0] * 5) is None

    def test_constant_prices_have_zero_volatility(self) -> None:
        assert _annualised_realised_vol([100.0] * 40) == pytest.approx(0.0)

    def test_annualises_by_root_252(self) -> None:
        """Volatility accumulates on trading days, not calendar days."""
        daily_moves = [100.0 * (1.01 if i % 2 else 1.0 / 1.01) for i in range(60)]
        result = _annualised_realised_vol(daily_moves)
        assert result is not None

        returns = [math.log(b / a) for a, b in itertools.pairwise(daily_moves)]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        assert result == pytest.approx(math.sqrt(variance) * math.sqrt(252.0))

    def test_ignores_non_positive_prices(self) -> None:
        """A zero close would make the log return undefined."""
        assert _annualised_realised_vol([100.0, 0.0, 101.0] + [100.0] * 40) is not None


class TestSymbolValidation:
    @pytest.mark.parametrize("symbol", ["", "   ", "A" * 20, "DROP TABLE", "AA;PL", "../etc"])
    def test_malformed_symbols_are_refused_without_a_network_call(self, symbol: str) -> None:
        """Rejected before anything leaves the process."""
        service = MarketDataService(make_settings())
        with pytest.raises(MarketDataUnavailableError):
            service.get_quote(symbol)

    @pytest.mark.parametrize("symbol", ["AAPL", "VOD.L", "^GSPC", "BRK-B", "EURUSD=X"])
    def test_real_world_symbol_shapes_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch, symbol: str, prices: list[float]
    ) -> None:
        """Indices, foreign listings, share classes and FX pairs all use punctuation."""
        install_fake_yfinance(monkeypatch, prices)
        service = MarketDataService(make_settings())
        quote, _ = service.get_quote(symbol)
        assert quote.symbol == symbol.upper()


class TestCaching:
    def test_second_lookup_is_served_from_cache(
        self, monkeypatch: pytest.MonkeyPatch, prices: list[float]
    ) -> None:
        install_fake_yfinance(monkeypatch, prices)
        service = MarketDataService(make_settings())

        first, hit_first = service.get_quote("AAPL")
        second, hit_second = service.get_quote("aapl")

        assert hit_first is False
        assert hit_second is True, "a repeat lookup must not hit the upstream again"
        assert first.spot == second.spot

    def test_symbols_are_normalised_before_caching(
        self, monkeypatch: pytest.MonkeyPatch, prices: list[float]
    ) -> None:
        install_fake_yfinance(monkeypatch, prices)
        service = MarketDataService(make_settings())
        service.get_quote("  aapl  ")
        assert service.cached_symbols() == 1
        _, hit = service.get_quote("AAPL")
        assert hit is True


class TestClientAvailability:
    """`is_enabled` and `client_available` answer different questions.

    Conflating them is what let a container report itself ready while the ticker
    lookup was dead, so the difference is pinned down here.
    """

    def test_reports_available_when_the_client_is_importable(self) -> None:
        service = MarketDataService(make_settings())
        assert service.client_available() is (importlib.util.find_spec("yfinance") is not None)

    def test_reports_unavailable_when_the_module_is_stubbed_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "yfinance", None)
        assert MarketDataService(make_settings()).client_available() is False

    def test_enabled_and_available_are_independent(
        self, monkeypatch: pytest.MonkeyPatch, prices: list[float]
    ) -> None:
        """Switched off in config, but the client is still installed."""
        install_fake_yfinance(monkeypatch, prices)
        service = MarketDataService(make_settings(market_data_enabled=False))
        assert service.is_enabled() is False
        assert service.client_available() is True


class TestFailureModes:
    def test_disabled_service_explains_the_manual_fallback(self) -> None:
        service = MarketDataService(make_settings(market_data_enabled=False))
        assert service.is_enabled() is False
        with pytest.raises(MarketDataUnavailableError, match="manually"):
            service.get_quote("AAPL")

    def test_upstream_exception_becomes_the_typed_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Callers must never have to know what yfinance raises."""
        install_fake_yfinance(monkeypatch, raises=TimeoutError("read timed out"))
        service = MarketDataService(make_settings())
        with pytest.raises(MarketDataUnavailableError, match="try again shortly"):
            service.get_quote("AAPL")

    def test_empty_history_suggests_checking_the_symbol(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unknown ticker returns an empty frame rather than an error."""
        install_fake_yfinance(monkeypatch, [])
        service = MarketDataService(make_settings())
        with pytest.raises(MarketDataUnavailableError, match="ticker symbol"):
            service.get_quote("NOTATICKER")

    def test_all_nan_history_is_treated_as_unusable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_yfinance(monkeypatch, [float("nan"), float("nan"), 0.0])
        service = MarketDataService(make_settings())
        with pytest.raises(MarketDataUnavailableError, match="usable closing prices"):
            service.get_quote("AAPL")

    def test_missing_client_library_is_reported_clearly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """yfinance is an optional extra, so the production image may not have it."""
        monkeypatch.setitem(sys.modules, "yfinance", None)
        service = MarketDataService(make_settings())
        with pytest.raises(MarketDataUnavailableError, match=r"not installed|manually"):
            service.get_quote("AAPL")


class TestQuoteContents:
    def test_quote_carries_the_latest_close_and_a_volatility_estimate(
        self, monkeypatch: pytest.MonkeyPatch, prices: list[float]
    ) -> None:
        install_fake_yfinance(monkeypatch, prices, currency="GBP")
        service = MarketDataService(make_settings())
        quote, _ = service.get_quote("VOD.L")

        assert quote.spot == pytest.approx(prices[-1])
        assert quote.currency == "GBP"
        assert quote.source == "yfinance"
        assert quote.realised_vol_30d is not None
        assert 0.0 < quote.realised_vol_30d < 5.0
        assert quote.as_of.endswith("+00:00"), "timestamps must be explicit UTC"
