"""The deployment entrypoint is a real thing that can break, so it gets a test.

`app.py` at the backend root exists solely so that a platform which loads an ASGI
application by file path can find one (see the docstring there). Nothing else in
the codebase imports it, which means a rename or a bad refactor would leave it
broken and the only symptom would be a failed deployment. These two tests turn
that into a failed build instead.
"""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_entrypoint_exposes_the_application() -> None:
    """The name and type a loader looks for are both what it expects."""
    module = importlib.import_module("app")

    assert isinstance(module.app, FastAPI)


def test_entrypoint_serves_requests() -> None:
    """Importable is not the same as working - so price something through it."""
    module = importlib.import_module("app")
    client = TestClient(module.app)

    response = client.post(
        "/api/v1/price",
        json={
            "option": {
                "spot": 100.0,
                "strike": 100.0,
                "time_to_expiry": 1.0,
                "risk_free_rate": 0.05,
                "volatility": 0.2,
            },
            "model": "black_scholes",
        },
    )

    assert response.status_code == 200
    # The canonical Black-Scholes value for the standard contract. If this holds
    # through the entrypoint, every layer between the loader and the maths works.
    assert response.json()["price"] == 10.450583572185565
