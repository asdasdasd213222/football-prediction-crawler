# P1-01 Configuration Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load a YAML source configuration into strict, typed models before any runtime component uses it.

**Architecture:** `multisite_crawler.config` owns parsing and validation only. Pydantic models reject unknown fields and invalid values; `load_config(path)` converts file and validation failures to a readable `ConfigurationError` without echoing config values.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, Pytest, Ruff, Mypy.

## Global Constraints

- Execute P1-01 only; do not add scheduling, fetching, adapters, persistence, migrations, or deployment behavior.
- Support `polling`, `rss`, `websocket`, and `sse`; enforce a minimum polling interval of 60 seconds.
- Do not place credentials, tokens, cookies, account data, or production values in examples, tests, or errors.
- Required checks are `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config`.

---

### Task 1: Specify Validation with Failing Tests

**Files:**
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `ConfigurationError`, `CrawlerConfig`, `SourceMode`, and `load_config` from `multisite_crawler.config`.
- Produces: executable expectations for valid and invalid YAML configuration.

- [ ] **Step 1: Write tests for successful loading and all supported modes**

```python
def test_load_config_returns_typed_sources(tmp_path: Path) -> None:
    path = write_config(tmp_path, mode="polling")

    config = load_config(path)

    assert isinstance(config, CrawlerConfig)
    assert config.sources[0].id == "demo_api"
    assert config.sources[0].mode is SourceMode.POLLING


@pytest.mark.parametrize("mode", ["polling", "rss", "websocket", "sse"])
def test_load_config_supports_each_mode(tmp_path: Path, mode: str) -> None:
    config = load_config(write_config(tmp_path, mode=mode))

    assert config.sources[0].mode.value == mode
```

- [ ] **Step 2: Write tests for duplicate IDs, interval, missing fields, and unknown fields**

```python
@pytest.mark.parametrize(
    ("replacement", "expected"),
    [
        ("interval_seconds: 59", "interval_seconds"),
        ("request:\n      url: https://example.invalid/items", "timeout_seconds"),
        ("unexpected: value", "unexpected"),
    ],
)
def test_load_config_reports_invalid_fields(
    tmp_path: Path, replacement: str, expected: str
) -> None:
    path = write_config(tmp_path, replacement=replacement)

    with pytest.raises(ConfigurationError, match=expected):
        load_config(path)
```

- [ ] **Step 3: Run tests to verify failure**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_config.py -q`

Expected: FAIL because `multisite_crawler.config` does not exist.

### Task 2: Implement the Strict Configuration API

**Files:**
- Create: `src/multisite_crawler/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `ConfigurationError`, `SourceMode`, `QueueName`, `RequestConfig`, `RetryConfig`, `RateLimitConfig`, `CircuitBreakerConfig`, `SourceConfig`, `CrawlerConfig`, and `load_config(path: Path) -> CrawlerConfig`.

- [ ] **Step 1: Define strict models and loader**

```python
class SourceMode(StrEnum):
    POLLING = "polling"
    RSS = "rss"
    WEBSOCKET = "websocket"
    SSE = "sse"


class QueueName(StrEnum):
    HTTP = "http"
    BROWSER = "browser"


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be safely loaded."""


def load_config(path: Path) -> CrawlerConfig:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(f"Cannot read configuration file: {path}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML in configuration file: {path}") from error

    if not isinstance(document, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")

    try:
        return CrawlerConfig.model_validate(document)
    except ValidationError as error:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        )
        raise ConfigurationError(f"Invalid configuration in {path}: {messages}") from error
```

- [ ] **Step 2: Verify focused tests pass**

Run: `.venv\\Scripts\\python.exe -m pytest tests/test_config.py -q`

Expected: PASS with all configuration tests passing.

### Task 3: Add Dependencies, Example, and User Documentation

**Files:**
- Modify: `pyproject.toml`
- Create: `configs/sources.example.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: the model field names from `multisite_crawler.config`.
- Produces: installable runtime dependencies and a safe configuration reference.

- [ ] **Step 1: Add runtime dependencies**

```toml
dependencies = [
    "pydantic>=2.8,<3",
    "PyYAML>=6.0,<7",
]
```

- [ ] **Step 2: Add a non-sensitive example source**

```yaml
sources:
  - id: demo_api
    name: Demo API
    enabled: true
    mode: polling
    interval_seconds: 60
    queue: http
    request:
      url: https://example.invalid/api/items
      method: GET
      timeout_seconds: 30
    retry:
      max_attempts: 3
      base_delay_seconds: 2
      max_delay_seconds: 30
    circuit_breaker:
      failure_threshold: 5
      recovery_seconds: 600
```

- [ ] **Step 3: Document loading and validation boundaries**

Add a README section naming `configs/sources.example.yaml` and showing
`load_config(Path("configs/sources.example.yaml"))`. State that configuration
loading validates only and does not start collection.

### Task 4: Verify Acceptance and Record P1-01

**Files:**
- Modify: `TODO.md`

**Interfaces:**
- Consumes: passing tests and quality-gate results.
- Produces: P1-01 completion state.

- [ ] **Step 1: Run all mandatory checks**

Run: `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config`.

Expected: every command exits with status `0`.

- [ ] **Step 2: Mark P1-01 after acceptance passes**

Change every P1-01 implementation and acceptance checkbox, plus its current execution-order entry, from `[ ]` to `[x]`.
