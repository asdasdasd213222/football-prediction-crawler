# Dedicated Edge Session Management Design

## Goal

Manage the lifecycle of an authorized, manually authenticated dedicated Edge
profile without reading, exporting, logging, or storing its credentials,
cookies, tokens, account data, or browser storage state.

## Scope

P4-02 adds only generic session-state management for the P4-01 host browser
runtime. It does not navigate to a real source, automate login, implement a
source adapter, bypass access controls, or approve `sporttery_zqspf` for P3-04.

## Decision

Each browser worker uses one dedicated Edge profile outside the repository.
An authorized operator manually opens that profile, completes any permitted
login in the browser, closes Edge, and records a non-sensitive profile refresh
event. The system never receives the credential or session material.

Redis stores only a profile reference, a Beijing-local manual-refresh time, and
the latest generic session state. The reference is an opaque configured name,
not an absolute path, account identifier, or source URL.

## State Contract

```text
unknown -> ready
unknown -> login_required | access_denied | captcha
ready   -> login_required | access_denied | captcha
failed  -> ready (only after an operator records a manual refresh)
```

The valid states are `unknown`, `ready`, `login_required`, `access_denied`, and
`captcha`. `login_required`, `access_denied`, and `captcha` are terminal
human-review outcomes for a collection attempt. They are never retried as a
login operation and they never trigger credential handling.

An adapter later supplies a `BrowserSessionObservation` containing only one of
these generic outcomes and a safe reason label. Site selectors and page text
remain inside that adapter. The generic P4-02 layer maps the observation to a
typed outcome, persists non-sensitive state, and makes the task stop explicitly.

## Components

- `browser_session.py` defines immutable session state values, a Redis-sized
  store protocol, state serialization, and safe state transitions.
- `BrowserSessionManager` records an operator refresh in `Asia/Shanghai`,
  reads the latest state, and records terminal human-review outcomes.
- `BrowserSessionRequiredError` carries only profile reference, generic state,
  and safe reason. It never includes page HTML, URL query values, account data,
  or credentials.
- A PowerShell helper validates the dedicated external profile settings and
  opens the configured Edge executable at `about:blank`; the operator performs
  any permitted login manually. The helper can record the refresh timestamp but
  cannot accept a username or password argument.

## Security And Operations

- Profile directories, screenshot directories, fixture directories, and source
  code remain separate. The helper rejects a repository-local profile.
- No `.env` value contains credentials. `BROWSER_PROFILE_REFERENCE` is an
  opaque non-secret identifier such as `sporttery_primary`.
- Session-state text is restricted to the fixed state vocabulary and safe
  reason labels. Tests scan serialized values and error strings for cookie,
  authorization, token, password, and account markers.
- A manual refresh is idempotent: repeated operator confirmations update only
  the refresh timestamp and reset state to `ready`.
- A future approved non-interactive login may read credentials only from an
  approved secret manager or environment variables. P4-02 provides no such
  login flow and does not add credential fields to configuration.
- A terminal observation raises an explicit domain failure for the worker's
  existing operational error path and never schedules a login retry.

## Verification

Unit tests use an in-memory Redis-shaped store and local fake observations.
They cover manual refresh, state persistence, login-required, 401/403,
CAPTCHA, safe failure, idempotent repeat refresh, and sensitive-string
rejection. A local acceptance check validates the dedicated profile path and
helper command without opening a real source. P3-04 remains blocked until its
source card has readable robots guidance, an external authorization record, and
an approved polling cadence.
