# Browser-First Edge Data Pipeline Design

## Goal

Make an authorized browser-monitored page a durable project data source without
coupling website-specific parsing to scheduling, queues, storage, or a user's
daily browser session.

## Scope

This design covers the runtime path required before implementing the
`sporttery_zqspf` adapter. It does not authorize production deployment, bypass
login, CAPTCHA, source enablement review, rate limits, or access controls.

## Decision

The project will run a dedicated local Microsoft Edge worker for browser-only
sources. Its default is public-visible monitoring: a no-login, user-equivalent
page refresh that reads only configured visible fields. It does not inspect
cookies, network traffic, hidden APIs, or a user's daily browser session. For a
source that permits this visible workflow, the project-owned monitor is the
durable data transport.
The existing Codex browser monitor remains an observation and acceptance aid;
it is not the project's production transport or durable data store.

The worker will launch Edge with a dedicated no-login profile directory outside
the repository. No worker attaches to an everyday Edge window, extracts
cookies, or copies session material. Manual login is a separate P4-02 feature
for a future source that has independently passed its source review; it is not
part of the public-visible monitoring mode.

## Data Flow

```text
Scheduler -> Redis browser queue -> source lease -> managed Edge session
          -> source adapter -> AdapterRunner -> RecordRepository -> PostgreSQL
```

The browser worker owns lifecycle, timeouts, resource limits, retry boundaries,
redaction, and cleanup. A source adapter owns only the page refresh action,
page-ready condition, table selector, source field mapping, and stable business
identifier rule. `RecordRepository` remains the sole owner of deduplication and
change-event persistence.

For browser sources, `fetch()` returns a `FetchResult` whose body is the
minimal, redacted source table fragment needed by that adapter. The adapter must
not return the account header, cookies, authorization data, or an unrestricted
page dump. Failure snapshots are redacted before persistence and remain outside
Git.

## Edge Runtime Contract

- The worker uses locally installed Microsoft Edge through the Playwright
  executable-path configuration; it does not attach over CDP to a user window.
- `BROWSER_USER_DATA_DIR` identifies a dedicated local profile directory and is
  required only by the browser worker. It is ignored by Git and is never logged.
- Public-visible monitoring never performs a login. A login prompt, CAPTCHA,
  401, 403, or access-control content is a terminal human-review outcome. The
  system records only the profile refresh time, never profile contents.
- The worker runs one configured browser source per Redis lease. It sets bounded
  page and action timeouts, never waits indefinitely for `networkidle`, and
  closes page, context, and browser resources in `finally` paths.
- CAPTCHA, login loss, 401, 403, and access-control content are terminal
  human-review outcomes. They do not trigger automated login, retries, or
  bypasses.

## Configuration And Boundaries

Browser-backed sources keep `queue: browser`, polling intervals of at least 60
seconds, and the existing per-source retry, rate-limit, and circuit-breaker
configuration. A source-specific browser transport block will contain only
non-secret operational values such as the Edge executable path, page timeout,
and a named profile reference. It must not contain usernames, passwords,
cookies, tokens, or absolute user-profile paths committed to Git.

The scheduler dispatches only the source ID. The task layer resolves the
validated source configuration and selects the generic browser runtime. Site
selectors and business mapping remain inside exactly one adapter per website.

## Implementation Order

1. Build and locally validate the generic dedicated-Edge runtime.
2. Add profile isolation, no-login failure handling, and redacted failure
   artifacts. Keep P4-02 manual-login operations optional and source-specific.
3. Reconfirm the external source enablement status and approved cadence, then implement
   the single `sporttery_zqspf` browser adapter with a redacted fixture.
4. Run local end-to-end acceptance followed by a 24-hour pre-production run.

## Acceptance Evidence

The browser runtime must pass offline lifecycle, timeout, cleanup, and
redaction tests. The source adapter must pass normal, empty, structural-change,
deduplication, update, retry, and rate-limit tests using redacted local
fixtures. A disposable PostgreSQL check must prove idempotent persistence.

Before any P3-04 source implementation, the source card must contain an
approved external enablement status, a non-secret external reference, and an
approved minimum polling interval. A selected browser-monitor transport does
not satisfy those source-specific conditions by itself. A 24-hour run is a
local pre-production acceptance check only; it is not a production deployment.
