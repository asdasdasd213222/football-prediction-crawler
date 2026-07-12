# P1-03 And P1-04 Adapter And Change Detection Design

## Scope

Implement the site-neutral adapter contract and the database-backed
deduplication and change-detection service. The work stops before scheduling,
queues, browser automation, real websites, credentials, and deployment.

## Adapter Contract

`multisite_crawler.adapters` will define a synchronous `BaseAdapter` with the
ordered operations `fetch`, `parse`, `normalize`, and `fingerprint`. Adapters
are the only location for source-specific parsing and field mapping. A generic
runner invokes the operations, validates every boundary, and returns a typed
collection result; it never writes to the database.

`FetchResult` carries raw response bytes and optional `ETag` and
`Last-Modified` validators. `CrawlItem` is a strict Pydantic model with a
non-blank stable `external_id` and JSON-compatible normalized business `data`.
`AdapterRunError`, `FetchError`, `ParseError`, `NormalizationError`, and
`AdapterContractError` distinguish source and operation failures. A successful
empty collection is represented explicitly; missing required fields and
malformed values raise an error before any storage operation.

## Hashing And Source State

The generic service computes a SHA-256 raw-response hash from `FetchResult`
bytes and persists the latest ETag, Last-Modified value, and raw hash in a new
`source_fetch_states` table keyed by source. It canonicalizes business JSON by
sorting mapping keys, using compact JSON encoding, and rejecting unsupported
values. The item fingerprint is SHA-256 over that canonical business JSON.

Only `CrawlItem.data` contributes to the business fingerprint. Response
formatting, source-page noise, headers, and JSON key order therefore cannot
produce a business change event. Each adapter's `fingerprint` result must match
the generic canonical fingerprint; a mismatch is a contract failure.

## Persistence And Events

P1-04 adds a migration with `source_fetch_states`, `records.last_seen_at`, and
`records.missing_count`. A `RecordRepository` persists a successful adapter
result inside a transaction. It creates a `created` event for a new record,
creates an `updated` event only when the business fingerprint changes, and
creates no event when the fingerprint is unchanged. The response validators are
updated regardless of whether item content changes.

The repository uses the existing `(source_id, external_id)` unique constraint
as the database idempotency boundary. It serializes updates using row locks and
retries a unique-constraint race by rereading the winning record, so concurrent
delivery cannot create duplicate records or duplicate `created` events.

## Missing Records

Missing-record reconciliation runs only after a successful, complete adapter
collection. For every active record absent from that collection, it increments
`missing_count`. At a confirmed threshold of three consecutive successful
collections, it sets `is_active` to false and creates one `inactive` event.
Records are never physically deleted. Seeing an existing inactive record again
resets `missing_count`, restores `is_active`, and records an `updated` event
only when its business fingerprint has changed.

Fetch, parsing, normalization, validation, and incomplete-collection failures
do not increment missing counters or mark records inactive.

## Verification

Unit tests use an in-memory fake adapter to prove the ordered contract,
successful empty results, strict invalid-output rejection, stable canonical
hashes, and distinct error types. PostgreSQL integration tests prove migration
upgrade/downgrade/upgrade, repeated delivery idempotency, JSON key-order
stability, noise isolation, accurate created/updated/inactive events,
three-successful-run inactivity, recovery, and concurrent Upsert uniqueness.

All timestamps remain Beijing local time (`Asia/Shanghai`), and all required
repository quality checks plus Alembic migration verification run before either
work item is marked complete.
