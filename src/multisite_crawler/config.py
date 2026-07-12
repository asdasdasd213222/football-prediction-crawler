"""Strict source configuration models and YAML loading."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)


class SourceMode(StrEnum):
    """Supported source transport modes."""

    POLLING = "polling"
    RSS = "rss"
    WEBSOCKET = "websocket"
    SSE = "sse"


class QueueName(StrEnum):
    """Worker queue categories."""

    HTTP = "http"
    BROWSER = "browser"


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be safely loaded."""


class StrictModel(BaseModel):
    """Base model that refuses fields not declared by the configuration schema."""

    model_config = ConfigDict(extra="forbid")


class RequestConfig(StrictModel):
    """HTTP request settings for a source."""

    url: HttpUrl
    method: Literal["GET", "HEAD", "POST"]
    timeout_seconds: float = Field(gt=0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def require_numeric_timeout(cls, value: Any) -> float:
        return _require_number(value, "timeout_seconds")


class RetryConfig(StrictModel):
    """Retry policy for transient source failures."""

    max_attempts: StrictInt = Field(ge=1)
    base_delay_seconds: float = Field(gt=0)
    max_delay_seconds: float = Field(gt=0)

    @field_validator("base_delay_seconds", "max_delay_seconds", mode="before")
    @classmethod
    def require_numeric_delay(cls, value: Any) -> float:
        return _require_number(value, "retry delay")

    @model_validator(mode="after")
    def validate_delay_range(self) -> RetryConfig:
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be at least base_delay_seconds")
        return self


class RateLimitConfig(StrictModel):
    """A fixed-window per-source request limit."""

    max_requests: StrictInt = Field(ge=1)
    window_seconds: StrictInt = Field(ge=1)


class CircuitBreakerConfig(StrictModel):
    """Failure threshold and recovery window for a source."""

    failure_threshold: StrictInt = Field(ge=1)
    recovery_seconds: StrictInt = Field(ge=1)


class SourceConfig(StrictModel):
    """Configuration for a single source adapter."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    enabled: StrictBool
    mode: SourceMode
    interval_seconds: StrictInt = Field(ge=60)
    queue: QueueName
    request: RequestConfig
    retry: RetryConfig
    rate_limit: RateLimitConfig | None = None
    circuit_breaker: CircuitBreakerConfig

    @field_validator("id", "name")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class CrawlerConfig(StrictModel):
    """Root configuration for all enabled and disabled sources."""

    sources: list[SourceConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_source_ids(self) -> CrawlerConfig:
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source id")
        return self


def load_config(path: Path) -> CrawlerConfig:
    """Load a YAML file into a validated crawler configuration."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(f"Cannot read configuration file: {path}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(
            f"Invalid YAML in configuration file: {path}"
        ) from error

    if not isinstance(document, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")

    try:
        return CrawlerConfig.model_validate(document)
    except ValidationError as error:
        raise ConfigurationError(
            f"Invalid configuration in {path}: {_validation_messages(error)}"
        ) from error


def _require_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must be a number")
    return float(value)


def _validation_messages(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()
    )
