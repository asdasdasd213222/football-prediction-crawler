---
name: crawler-adapter
description: Build one repository-compliant source adapter for an authorized source.
---

# Crawler Adapter Skill

Use this skill only for one selected source-adapter TODO item. It produces a
reviewable change; it never deploys a source or enables production collection.

## Required Inputs

Read `AGENTS.md`, `TODO.md`, the selected source card in `docs/sources/`, the
current adapter contract, comparable adapters, relevant fixtures, and the
source configuration before editing. Stop for human review when source
authorization, terms, robots guidance, permitted cadence, or the required
fields are unclear.

State the source id, allowed data fields, stable external-id rule, approved
access method, permitted polling interval, and expected empty-result behavior.
Do not infer any of these values from a page or an account session.

## Access Decision

Choose the first approved option in this order: official API, webhook,
WebSocket, SSE, RSS, ordinary HTTP, then the repository-managed dedicated
browser worker. Browser automation is allowed only when the source card and
runtime contract explicitly require it.

Never bypass a CAPTCHA, login, paywall, robots rule, access control, rate
limit, or another site restriction. Do not inspect cookies, browser storage,
passwords, tokens, or account data. Do not add a direct HTTP path when the
approved source contract is browser-only.

## Fixture Procedure

Preserve the smallest response fragment needed to exercise the parser. Before
adding a fixture, remove credentials, cookies, authorization headers, personal
data, query parameters, and unrelated page content. Store fixtures only under
`tests/fixtures/`; never store failure snapshots or browser profiles in Git.

Document fixture provenance, redaction performed, and its expected parser
outcome in the test. A fixture is a regression input, not evidence of ongoing
source authorization.

## Implementation Procedure

1. Place all selectors, field mappings, and source-specific parsing in exactly
   one class below `src/multisite_crawler/adapters/`.
2. Implement `fetch`, `parse`, `normalize`, and `fingerprint` from
   `BaseAdapter`. Return `FetchResult`, source-shaped mappings, `CrawlItem`,
   and `fingerprint_business_data(item.data)` respectively.
3. Keep scheduler, queue, retry, metrics, and persistence code site-neutral.
4. Raise explicit `FetchError`, `ParseError`, or a contract error with source
   operation context. Do not swallow an exception or log response text.
5. Keep the external identifier stable, validate output before persistence,
   and preserve idempotency through the shared runner and repository.

## Test Matrix

Add focused tests for normal data, empty results, malformed or missing fields,
network failure, duplicate collection, a business update, and the approved
rate-limit or access-denied behavior. Use only the local Mock Server or
fixtures unless the selected TODO explicitly authorizes another test target.

Run the full repository gates:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -q
docker compose config
```

Run the Alembic upgrade, downgrade-one, and upgrade checks whenever a database
change is part of the selected item.

## Monitoring And Safety

Use the existing structured event and low-cardinality metric conventions. Log
only source id, run id, task id, outcome, duration, item count, and safe error
type. Preserve a redacted external failure snapshot on parser or browser
failure when the existing runtime boundary supports it.

Do not commit production keys, tokens, cookies, passwords, browser profiles,
database URLs, or real account data. Do not deploy, manually enable a source,
or change unrelated adapters.

## Existing Validation Examples

Validate the contract against both current repository examples before claiming
completion:

- `src/multisite_crawler/adapters/demo_api.py::DemoApiAdapter` exercised with
  `MockCrawlerServer`.
- `tests/test_adapters.py::FakeAdapter` exercised by `AdapterRunner`.

These examples cover a controlled source-specific adapter and a minimal
contract implementation without requiring a real website.

## Final Report

Report the selected TODO item, source id, approved access method, files
changed, fixture redaction, external-id and fingerprint rules, test matrix,
all command results, remaining risks, and human review points. State plainly
that no production deployment or restriction bypass was performed.
