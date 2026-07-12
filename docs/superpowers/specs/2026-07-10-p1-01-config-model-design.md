# P1-01 Configuration Model Design

## Scope

Provide strict, file-based validation for source configuration. This task reads YAML and returns typed configuration models; it does not schedule, fetch, parse, store, or deploy data.

## Model

`multisite_crawler.config` will expose Pydantic v2 models and a `load_config(path)` loader. The root configuration contains a non-empty `sources` list. Each source has a unique non-empty `id`, display `name`, boolean `enabled`, a collection `mode`, an interval of at least 60 seconds, and a queue selection.

The model includes nested request, retry, rate-limit, and circuit-breaker settings. Request URLs are HTTP or HTTPS URLs; timeout and rate-limit values are positive; retry and circuit-breaker values have non-negative or positive limits appropriate to their field. Supported modes are `polling`, `rss`, `websocket`, and `sse`; supported queues are `http` and `browser`.

All models reject unknown fields and type coercion. The loader uses `yaml.safe_load`, rejects an empty or non-mapping document, and converts YAML, I/O, and validation failures to a readable `ConfigurationError` that identifies the source file without echoing its contents.

## Dependencies And Documentation

Add Pydantic and PyYAML as runtime dependencies. Add a non-sensitive example source configuration under `configs/` and document the file format and Python loader entry point in the README.

## Verification

Tests cover a valid document, each supported mode, duplicate source IDs, an interval below 60 seconds, a missing required field, and unknown fields. The existing Ruff, Mypy, Pytest, and Compose checks remain required before P1-01 is checked in `TODO.md`.
