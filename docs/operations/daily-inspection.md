# Daily Inspection

The `Daily Inspection` GitHub Actions workflow is a P7 read-only diagnostic
automation. It runs daily at 00:17 UTC, which is 08:17 Beijing time, and may be
started manually from the Actions tab. It does not collect source data, access
browser profiles, query databases or Redis, read repository secrets, merge
pull requests, or deploy an environment.

## Input Contract

Configure the repository variable `INSPECTION_REPORT_URL` only after an
approved read-only HTTPS endpoint is available. The endpoint must return one
aggregate JSON document for the preceding 24 hours. It must not require a
credential, and it must contain only the fields in this shape:

```json
{
  "window_end": "2026-07-13T08:00:00+08:00",
  "sources": [
    {
      "source_id": "example_source",
      "runs_succeeded": 24,
      "runs_failed": 0,
      "last_success_at": "2026-07-13T07:59:00+08:00",
      "average_duration_seconds": 0.25,
      "p95_duration_seconds": 0.5,
      "item_count": 12,
      "baseline_item_count": 12,
      "parse_failure_snapshot_count": 0,
      "http_statuses": {"401": 0, "403": 0, "429": 0},
      "queue_depth": 0,
      "circuit_breaker_open": false
    }
  ]
}
```

All timestamps must include a timezone and are normalized to `Asia/Shanghai`.
The contract rejects all unknown fields, URLs, snapshot paths, source payloads,
headers, credentials, cookies, account data, and secrets. It reports aggregate
snapshot counts only; a human reviews the redacted external snapshot through
the normal operational procedure.

Until the endpoint exists, the workflow produces a concise configuration note
and does not open an issue. This repository has no approved production source,
so the endpoint itself is intentionally not configured in P7.

## Findings And Actions

The report evaluates failure rate, last successful run, item-count deviation,
new parser-failure snapshot count, HTTP 401/403/429 counts, queue depth, and
circuit-breaker state. An `attention` report creates or updates one GitHub
Issue titled `Crawler daily inspection requires review`. A `healthy` report is
only written to the workflow summary.

The workflow permissions are limited to `contents: read` and `issues: write`.
Its ephemeral GitHub token cannot read production secrets and cannot write
repository contents, merge pull requests, create releases, or deploy. Any
repair remains a separate reviewed branch using the `crawler-repair` skill.
