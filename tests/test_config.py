from __future__ import annotations

from pathlib import Path
from textwrap import indent

import pytest

from multisite_crawler.config import (
    ConfigurationError,
    CrawlerConfig,
    SourceMode,
    load_config,
)


def source_yaml(
    *,
    mode: str = "polling",
    source_id: str = "demo_api",
    interval_seconds: int = 60,
    include_timeout: bool = True,
) -> str:
    timeout = "  timeout_seconds: 30\n" if include_timeout else ""
    return (
        f"id: {source_id}\n"
        "name: Demo API\n"
        "enabled: true\n"
        f"mode: {mode}\n"
        f"interval_seconds: {interval_seconds}\n"
        "queue: http\n"
        "request:\n"
        "  url: https://example.invalid/api/items\n"
        "  method: GET\n"
        f"{timeout}"
        "retry:\n"
        "  max_attempts: 3\n"
        "  base_delay_seconds: 2\n"
        "  max_delay_seconds: 30\n"
        "rate_limit:\n"
        "  max_requests: 60\n"
        "  window_seconds: 60\n"
        "circuit_breaker:\n"
        "  failure_threshold: 5\n"
        "  recovery_seconds: 600\n"
    )


def write_config(tmp_path: Path, *sources: str, suffix: str = "") -> Path:
    path = tmp_path / "sources.yaml"
    document = "sources:\n" + "\n".join(
        f"  - {indent(source, '    ').lstrip()}" for source in sources
    )
    path.write_text(document + suffix, encoding="utf-8")
    return path


def test_load_config_returns_typed_sources(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, source_yaml()))

    assert isinstance(config, CrawlerConfig)
    assert config.sources[0].id == "demo_api"
    assert config.sources[0].mode is SourceMode.POLLING


@pytest.mark.parametrize("mode", ["polling", "rss", "websocket", "sse"])
def test_load_config_supports_each_mode(tmp_path: Path, mode: str) -> None:
    config = load_config(write_config(tmp_path, source_yaml(mode=mode)))

    assert config.sources[0].mode.value == mode


def test_load_config_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    path = write_config(tmp_path, source_yaml(), source_yaml())

    with pytest.raises(ConfigurationError, match="duplicate source id"):
        load_config(path)


def test_load_config_rejects_interval_below_sixty_seconds(tmp_path: Path) -> None:
    path = write_config(tmp_path, source_yaml(interval_seconds=59))

    with pytest.raises(ConfigurationError, match="interval_seconds"):
        load_config(path)


def test_load_config_reports_missing_required_field(tmp_path: Path) -> None:
    path = write_config(tmp_path, source_yaml(include_timeout=False))

    with pytest.raises(ConfigurationError, match="timeout_seconds"):
        load_config(path)


def test_load_config_rejects_unknown_fields(tmp_path: Path) -> None:
    path = write_config(tmp_path, source_yaml(), suffix="unknown: value\n")

    with pytest.raises(ConfigurationError, match="unknown"):
        load_config(path)
