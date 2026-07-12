# P0-02 AGENTS Contract Design

## Scope

Expand the repository-level `AGENTS.md` from bootstrap guidance into a concise,
enforceable engineering contract for the multi-site data collection system. This
task creates no collection, scheduler, adapter, database, or deployment code.

## Contract

The document will define the project's production-oriented goal and explicit
non-goals, the responsibility of each top-level directory, and the rule that
every website-specific behavior belongs to one adapter. Shared orchestration and
storage layers must remain site-neutral.

It will require idempotent task execution, redacted failure snapshots, and
ordinary HTTP or documented feeds before browser automation. Exceptions must
retain context and propagate through an explicit failure path; credentials and
access-control bypasses are forbidden.

The contract will require strict configuration and quality verification,
reversible database migrations when storage is introduced, documentation updates
for behavior changes, and human review before production deployment. A closer
`AGENTS.md` may add rules for a subdirectory but cannot weaken this contract.

## Acceptance

A new agent can read `AGENTS.md` and identify the architecture boundaries,
required commands, security limits, migration rules, and Definition of Done.
The document contains no endpoint credentials, account information, cookies,
tokens, or production environment values. P0-02 is checked in `TODO.md` only
after the document is reviewed and existing quality checks remain green.
