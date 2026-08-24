"""Application configuration, read from the environment.

Twelve-factor: every deployment-specific value arrives as an environment variable,
nothing is read from a file that would have to be baked into the image, and the
defaults are the ones that make local development work with no configuration at all.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPT_", env_file=".env", extra="ignore", frozen=True
    )

    app_name: str = "Options Pricing API"
    version: str = "1.0.0"

    # Populated by the Docker build from the build context so a running container can
    # report exactly which commit it came from.
    git_sha: str = Field(default="unknown")
    build_time: str = Field(default="unknown")

    # Only needed if the SPA calls the API cross-origin. In the intended deployment
    # the frontend is proxied onto the same origin by a Vercel rewrite, so this stays
    # empty and no CORS headers are emitted at all.
    cors_origins: list[str] = Field(default_factory=list)

    # Market data
    market_data_enabled: bool = True
    market_data_timeout_s: float = 3.0
    market_cache_ttl_s: int = 900  # 15 minutes
    market_cache_size: int = 256

    # Guard rails on the expensive endpoints, so a hand-crafted request cannot pin a
    # CPU on a free-tier container.
    max_binomial_steps: int = 5000
    max_monte_carlo_paths: int = 2_000_000
    max_convergence_steps: int = 400
    max_convergence_paths: int = 200_000


@lru_cache
def get_settings() -> Settings:
    """Cached accessor, so the environment is parsed once per process."""
    return Settings()
