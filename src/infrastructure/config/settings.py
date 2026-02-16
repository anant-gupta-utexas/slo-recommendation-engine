"""Application configuration using Pydantic Settings.

Centralized configuration management following Clean Architecture principles.
All environment variables should be accessed through this module.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    model_config = SettingsConfigDict(env_prefix="DB_", case_sensitive=False)

    url: str = Field(
        ...,
        alias="DATABASE_URL",
        description="PostgreSQL connection URL",
    )
    pool_size: int = Field(
        default=20,
        description="Connection pool size",
    )
    max_overflow: int = Field(
        default=10,
        description="Maximum number of connections to create above pool_size",
    )
    echo: bool = Field(
        default=False,
        description="Enable SQL query logging (development only)",
    )


class RedisSettings(BaseSettings):
    """Redis configuration settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    cache_ttl: int = Field(
        default=300,
        description="Default cache TTL in seconds",
    )


class APISettings(BaseSettings):
    """API server configuration settings."""

    model_config = SettingsConfigDict(env_prefix="API_", case_sensitive=False)

    host: str = Field(
        default="0.0.0.0",
        description="Host to bind the API server",
    )
    port: int = Field(
        default=8000,
        description="Port to bind the API server",
    )
    workers: int = Field(
        default=4,
        description="Number of Uvicorn worker processes",
    )


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration settings."""

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", case_sensitive=False)

    ingestion: int = Field(
        default=10,
        description="Ingestion endpoint rate limit (requests per minute)",
    )
    query: int = Field(
        default=60,
        description="Query endpoint rate limit (requests per minute)",
    )


class ObservabilitySettings(BaseSettings):
    """Observability configuration settings (OpenTelemetry, logging, metrics)."""

    model_config = SettingsConfigDict(env_prefix="OTEL_", case_sensitive=False)

    # OpenTelemetry Tracing
    exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTLP exporter endpoint (gRPC)",
    )
    service_name: str = Field(
        default="slo-engine",
        description="Service name for traces and metrics",
    )
    trace_sample_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Trace sampling rate (0.0 to 1.0)",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_json_format: bool = Field(
        default=True,
        description="Enable JSON structured logging",
    )


class BackgroundTaskSettings(BaseSettings):
    """Background task configuration settings."""

    model_config = SettingsConfigDict(case_sensitive=False)

    otel_graph_ingest_interval_minutes: int = Field(
        default=15,
        description="OTel Service Graph ingestion interval (minutes)",
    )
    stale_edge_threshold_hours: int = Field(
        default=168,  # 7 days
        description="Threshold to mark edges as stale (hours)",
    )
    slo_batch_interval_hours: int = Field(
        default=24,
        description="SLO recommendation batch computation interval (hours)",
    )


class PrometheusSettings(BaseSettings):
    """Prometheus integration configuration (for OTel Service Graph)."""

    model_config = SettingsConfigDict(env_prefix="PROMETHEUS_", case_sensitive=False)

    url: str = Field(
        default="http://localhost:9090",
        description="Prometheus server URL",
    )
    timeout_seconds: int = Field(
        default=30,
        description="Query timeout in seconds",
    )


class Settings(BaseSettings):
    """Main application settings.

    Aggregates all configuration modules and provides a single settings object.
    Load from environment variables and .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    # Environment
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)",
    )

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api: APISettings = Field(default_factory=APISettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    observability: ObservabilitySettings = Field(
        default_factory=ObservabilitySettings
    )
    background_tasks: BackgroundTaskSettings = Field(
        default_factory=BackgroundTaskSettings
    )
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)


# Global settings instance (singleton)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get global settings instance (singleton pattern).

    Returns:
        Settings instance loaded from environment
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
