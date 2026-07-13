---
name: crawler-repair
description: Diagnose and repair one authorized crawler regression through a test-first workflow.
---

# Crawler Repair Skill

Use this skill for a diagnosed adapter or runtime regression only. It creates a
reviewable repair branch or report; it never merges, deploys, changes source
authorization, or resumes a disabled source.

## Required Evidence

Read `AGENTS.md`, `TODO.md`, the source card, the affected adapter, its tests,
the relevant structured run logs, and any redacted failure snapshot metadata.
Record the source id, crawl run id, task id, safe exception type, first failing
operation, and the last known successful run. Never copy response text,
credentials, cookies, account data, headers outside the allowlist, or browser
storage into a test or report.

## Diagnose Before Editing

Classify the incident before proposing code changes:

- Network or transient service failure: connection, timeout, 502, or 503.
- Access or session failure: 401, 403, 429, CAPTCHA, or an expired permitted
  manual session. Escalate for human review; do not retry as a login action.
- Page or response structure change: a parser field, expected element, or
  schema is absent or has an incompatible type.
- Data-quality anomaly: valid parsing with unexpected empty or abnormal counts.
- Unknown: create an investigation report and stop instead of guessing.

The diagnosis must distinguish a parser defect from an authorization or rate
limit problem. Do not modify selectors or parsing to conceal an access-control
response.

## Test-First Repair Procedure

1. Add or update one redacted fixture that reproduces the suspected parser
   regression. Preserve only the minimum safe structure.
2. Add a regression test and run it before changing parser code. It must fail
   for the intended reason.
3. Make the smallest source-specific change inside the affected adapter.
4. Re-run the regression test and the affected adapter tests; they must pass.
5. Run the full repository gates:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -q
docker compose config
```

Run migration verification as well when the selected repair changes database
schema or persistence behavior.

## Change Boundaries

Do not change unrelated adapters, shared scheduler behavior, queue behavior,
credentials, browser login behavior, production configuration, or deployment
workflows. Preserve source id, external-id stability, canonical fingerprinting,
idempotency, metrics, and redacted failure-snapshot handling.

Never bypass CAPTCHA, login, paywall, robots restrictions, access controls, or
rate limits. If the evidence is incomplete or a safe classification is not
possible, produce an investigation report with the next human review question
instead of a speculative patch.

## Repair Report

Report the incident evidence, diagnosis, fixture redaction, failing test before
the patch, minimal changed files, passing checks after the patch, residual
risk, and required human review. State that the repair was not merged or
deployed and that no restriction bypass was attempted.
