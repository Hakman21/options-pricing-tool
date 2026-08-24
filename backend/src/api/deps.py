"""Shared dependencies.

The market data service holds a process-wide cache, so it must be a singleton rather
than constructed per request. Exposing it through a FastAPI dependency (instead of a
module-level global that routers import directly) means tests can override it with
``app.dependency_overrides`` and never touch the network.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from .market_data import MarketDataService
from .settings import Settings, get_settings


@lru_cache
def get_market_data_service() -> MarketDataService:
    return MarketDataService(get_settings())


SettingsDep = Annotated[Settings, Depends(get_settings)]
MarketDataDep = Annotated[MarketDataService, Depends(get_market_data_service)]
