"""Tier 4: API contract tests.

These assert the shape of the HTTP surface, not the mathematics - that is already
covered without a web server. What matters here is that valid requests are accepted,
invalid ones are refused with a message worth showing a user, and an upstream outage
degrades into something the UI can handle.

Nothing here touches the network: the market data service is replaced through
FastAPI's dependency overrides.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.deps import get_market_data_service
from api.main import create_app
from api.market_data import MarketDataUnavailableError, Quote

VALID_OPTION = {
    "spot": 100.0,
    "strike": 100.0,
    "time_to_expiry": 1.0,
    "risk_free_rate": 0.05,
    "volatility": 0.2,
    "dividend_yield": 0.0,
    "option_type": "call",
    "exercise": "european",
}


class StubMarketData:
    """Deterministic stand-in for the yfinance-backed service."""

    def __init__(self, *, fail: bool = False, client_installed: bool = True) -> None:
        self.fail = fail
        self.client_installed = client_installed
        self.calls = 0

    def is_enabled(self) -> bool:
        return not self.fail

    def client_available(self) -> bool:
        return self.client_installed

    def cached_symbols(self) -> int:
        return 0

    def get_quote(self, symbol: str) -> tuple[Quote, bool]:
        self.calls += 1
        if self.fail:
            raise MarketDataUnavailableError(
                "Could not reach the market data provider. Enter values manually."
            )
        return (
            Quote(
                symbol=symbol.upper(),
                spot=187.42,
                currency="USD",
                realised_vol_30d=0.2431,
                as_of="2026-08-23T09:00:00+00:00",
                source="stub",
            ),
            False,
        )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_market_data_service] = lambda: StubMarketData()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def offline_client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_market_data_service] = lambda: StubMarketData(fail=True)
    with TestClient(app) as c:
        yield c


class TestProbes:
    def test_health_is_ok(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok"}

    def test_ready_reports_its_checks(self, client: TestClient) -> None:
        body = client.get("/ready").json()
        assert body["status"] == "ready"
        assert "pricing_library" in body["checks"]
        assert body["checks"]["market_data"] == "ok"

    def test_ready_reports_a_missing_market_data_client(self) -> None:
        """A deployment built without the `market` extra must say so here.

        Otherwise it looks healthy right up until someone types a ticker, which is
        precisely the failure this check exists to catch.
        """
        app = create_app()
        app.dependency_overrides[get_market_data_service] = lambda: StubMarketData(
            client_installed=False
        )
        with TestClient(app) as c:
            checks = c.get("/ready").json()["checks"]
        assert checks["market_data"] == "unavailable (client not installed)"

    def test_ready_distinguishes_disabled_from_broken(self) -> None:
        app = create_app()
        app.dependency_overrides[get_market_data_service] = lambda: StubMarketData(fail=True)
        with TestClient(app) as c:
            checks = c.get("/ready").json()["checks"]
        assert checks["market_data"] == "disabled by configuration"

    def test_meta_lists_every_model(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        assert {m["id"] for m in body["models"]} == {
            "black_scholes",
            "binomial",
            "monte_carlo",
        }
        american = next(m for m in body["models"] if m["supports_american"])
        assert american["id"] == "binomial"


class TestPricing:
    @pytest.mark.parametrize("model", ["black_scholes", "binomial", "monte_carlo"])
    def test_every_model_prices_and_returns_five_greeks(
        self, client: TestClient, model: str
    ) -> None:
        response = client.post(
            "/api/v1/price",
            json={"option": VALID_OPTION, "model": model, "params": {"paths": 20_000}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["price"] == pytest.approx(10.45, abs=0.15)
        assert set(body["greeks"]) == {"delta", "gamma", "vega", "theta", "rho"}
        assert body["compute_ms"] >= 0.0

    def test_only_monte_carlo_reports_an_error_estimate(self, client: TestClient) -> None:
        """A closed form has no sampling error; a simulation must never hide one."""
        closed = client.post(
            "/api/v1/price", json={"option": VALID_OPTION, "model": "black_scholes"}
        ).json()
        simulated = client.post(
            "/api/v1/price",
            json={"option": VALID_OPTION, "model": "monte_carlo", "params": {"paths": 20_000}},
        ).json()

        assert closed["standard_error"] is None
        assert closed["confidence_interval"] is None
        assert simulated["standard_error"] > 0.0
        low, high = simulated["confidence_interval"]
        assert low < simulated["price"] < high

    def test_compare_runs_all_three_and_measures_the_error(self, client: TestClient) -> None:
        body = client.post(
            "/api/v1/compare",
            json={"option": VALID_OPTION, "params": {"steps": 300, "paths": 50_000}},
        ).json()

        assert body["reference_model"] == "black_scholes"
        assert len(body["results"]) == 3
        assert body["unsupported"] == []

        closed_form = next(r for r in body["results"] if r["model"] == "black_scholes")
        assert closed_form["abs_error"] == pytest.approx(0.0, abs=1e-12)

        for row in body["results"]:
            assert abs(row["rel_error"]) < 0.01

    def test_compare_on_an_american_contract_explains_the_declines(
        self, client: TestClient
    ) -> None:
        """Two models declining is information, not a failure - so it is a 200."""
        body = client.post(
            "/api/v1/compare",
            json={"option": {**VALID_OPTION, "option_type": "put", "exercise": "american"}},
        ).json()

        assert body["reference_model"] == "binomial"
        assert [r["model"] for r in body["results"]] == ["binomial"]
        assert {u["model"] for u in body["unsupported"]} == {"black_scholes", "monte_carlo"}
        assert all(len(u["reason"]) > 20 for u in body["unsupported"])

    def test_convergence_returns_both_sweeps(self, client: TestClient) -> None:
        body = client.post(
            "/api/v1/convergence",
            json={"option": VALID_OPTION, "max_steps": 40, "max_paths": 20_000},
        ).json()

        assert len(body["binomial"]) > 10
        assert len(body["monte_carlo"]) >= 3
        # The lattice error must change sign, or the convergence chart is a lie.
        errors = [p["error"] for p in body["binomial"][:10]]
        assert any((a > 0) != (b > 0) for a, b in itertools.pairwise(errors))

    def test_payoff_curve_breaks_even_above_the_strike_for_a_call(self, client: TestClient) -> None:
        body = client.post("/api/v1/payoff", json={"option": VALID_OPTION}).json()
        assert body["breakeven"] == pytest.approx(body["strike"] + body["premium"], abs=1e-9)
        assert len(body["spots"]) == len(body["payoffs"]) == len(body["profits"])
        assert min(body["payoffs"]) == 0.0

    def test_sensitivity_curve_matches_the_requested_greek(self, client: TestClient) -> None:
        body = client.post(
            "/api/v1/sensitivity", json={"option": VALID_OPTION, "greek": "gamma"}
        ).json()
        assert body["greek"] == "gamma"
        assert all(v >= 0.0 for v in body["values"]), "gamma is never negative"

    def test_paths_endpoint_returns_the_requested_shape(self, client: TestClient) -> None:
        body = client.post(
            "/api/v1/paths", json={"option": VALID_OPTION, "n_paths": 12, "n_steps": 30}
        ).json()
        assert len(body["paths"]) == 12
        assert all(len(p) == 31 for p in body["paths"])
        assert len(body["times"]) == 31

    def test_implied_volatility_round_trips(self, client: TestClient) -> None:
        priced = client.post(
            "/api/v1/price", json={"option": VALID_OPTION, "model": "black_scholes"}
        ).json()["price"]
        body = client.post(
            "/api/v1/implied-vol",
            json={"option": VALID_OPTION, "market_price": priced},
        ).json()
        assert body["implied_volatility"] == pytest.approx(0.2, abs=1e-6)


class TestValidation:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("spot", 0.0),
            ("spot", -10.0),
            ("strike", 0.0),
            ("time_to_expiry", 0.0),
            ("time_to_expiry", 100.0),
            ("volatility", 0.0),
            ("volatility", 12.0),
            ("risk_free_rate", 5.0),
            ("dividend_yield", -0.1),
        ],
    )
    def test_out_of_domain_input_is_rejected_before_pricing(
        self, client: TestClient, field: str, value: float
    ) -> None:
        response = client.post(
            "/api/v1/price",
            json={"option": {**VALID_OPTION, field: value}, "model": "black_scholes"},
        )
        assert response.status_code == 422
        assert field in str(response.json())

    def test_unknown_model_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/v1/price", json={"option": VALID_OPTION, "model": "heston"})
        assert response.status_code == 422

    @pytest.mark.parametrize("model", ["black_scholes", "monte_carlo"])
    def test_american_exercise_is_refused_with_a_usable_message(
        self, client: TestClient, model: str
    ) -> None:
        """A wrong number would be worse than a refusal, and the message has to tell
        the user what to do instead."""
        response = client.post(
            "/api/v1/price",
            json={
                "option": {**VALID_OPTION, "exercise": "american"},
                "model": model,
                "params": {"paths": 5_000},
            },
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "UnsupportedFeatureError"
        assert "binomial" in body["detail"].lower()

    def test_lattice_step_bounds_are_enforced(self, client: TestClient) -> None:
        for steps in (2, 99_999):
            response = client.post(
                "/api/v1/price",
                json={"option": VALID_OPTION, "model": "binomial", "params": {"steps": steps}},
            )
            assert response.status_code == 422

    def test_unstable_lattice_returns_a_diagnosable_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/price",
            json={
                "option": {
                    **VALID_OPTION,
                    "time_to_expiry": 20.0,
                    "risk_free_rate": 0.9,
                    "volatility": 0.03,
                },
                "model": "binomial",
                "params": {"steps": 4},
            },
        )
        assert response.status_code == 422
        assert response.json()["error"] == "LatticeStabilityError"


class TestMarketData:
    def test_quote_is_returned_for_a_valid_symbol(self, client: TestClient) -> None:
        body = client.get("/api/v1/market/AAPL").json()
        assert body["symbol"] == "AAPL"
        assert body["spot"] == pytest.approx(187.42)
        assert body["realised_vol_30d"] == pytest.approx(0.2431)

    def test_outage_becomes_a_503_with_an_actionable_message(
        self, offline_client: TestClient
    ) -> None:
        """This is the failure the UI is built to survive: the manual-entry fallback
        depends on this status code and this message reaching the client."""
        response = offline_client.get("/api/v1/market/AAPL")
        assert response.status_code == 503
        assert "manually" in response.json()["detail"]

    def test_pricing_still_works_while_market_data_is_down(
        self, offline_client: TestClient
    ) -> None:
        """The whole point of the boundary: a dead upstream must not take the tool
        with it."""
        response = offline_client.post(
            "/api/v1/price", json={"option": VALID_OPTION, "model": "black_scholes"}
        )
        assert response.status_code == 200


class TestOpenApiContract:
    def test_schema_is_generated_and_complete(self, client: TestClient) -> None:
        """The frontend's TypeScript types are generated from this document, so it
        has to be present and describe every route."""
        schema = client.get("/api/openapi.json").json()
        paths = schema["paths"]
        for route in (
            "/health",
            "/ready",
            "/api/v1/meta",
            "/api/v1/price",
            "/api/v1/compare",
            "/api/v1/convergence",
            "/api/v1/payoff",
            "/api/v1/sensitivity",
            "/api/v1/paths",
            "/api/v1/implied-vol",
            "/api/v1/market/{symbol}",
        ):
            assert route in paths, f"{route} missing from the OpenAPI document"

    def test_docs_are_served(self, client: TestClient) -> None:
        assert client.get("/api/docs").status_code == 200
