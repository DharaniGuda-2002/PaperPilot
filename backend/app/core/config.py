from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local .env)."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    db_connect_timeout_seconds: int = 3

    # Abuse limits for the public demo.
    max_request_body_bytes: int = 16_384
    create_rate_limit_per_minute: int = 5  # per client IP, per API process
    daily_investigation_cap: int = 200  # across all clients, rolling 24 hours
    paper_search_rate_limit_per_minute: int = 20  # per client IP, per API process

    # OpenAlex. Without a key, calls share a small daily budget per outbound IP.
    # "fixture" serves a recorded sample for every query: automated tests only.
    paper_provider: Literal["openalex", "fixture"] = "openalex"
    fixture_provider_latency_ms: int = 0  # benchmarks only
    openalex_base_url: str = "https://api.openalex.org"
    openalex_api_key: str | None = None
    openalex_contact_email: str | None = None
    paper_search_cache_hours: int = 24
    daily_provider_call_cap: int = 500  # uncached searches per rolling 24 hours

    # Kafka and background workers (local deployment).
    kafka_bootstrap_servers: str = "127.0.0.1:9094"  # IPv4: compose publishes on 127.0.0.1 only
    outbox_batch_size: int = 100
    outbox_poll_seconds: float = 1.0
    outbox_lease_seconds: float = 30.0
    discovery_papers_per_investigation: int = 25
    discovery_max_attempts: int = 4
    retry_base_seconds: float = 30.0
    retry_max_seconds: float = 900.0
    # A message whose handler raises this many times in a row is dead-lettered
    # so one bad message cannot block its partition.
    consumer_max_handler_failures: int = 5
    # "sentence-transformers" (real model) or "hashing" (tests/CI only).
    embedding_provider: Literal["sentence-transformers", "hashing"] = "sentence-transformers"
    # Off: never fetch PDFs, use abstracts only (CI with recorded data, or hosts that
    # should make no outbound document requests).
    document_fetch_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        # Hosted Postgres providers hand out postgres:// or postgresql:// URLs;
        # SQLAlchemy needs the driver named explicitly.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
