# P7 Codex Capability Design

## Scope

P7 turns the repository's adapter and repair practices into versioned skill
contracts and adds a read-only daily inspection path. It does not add a real
source, credentials, login automation, or a production deployment.

## Skill Contracts

The adapter skill is a complete change procedure: approved input evidence,
access selection, fixture redaction, `BaseAdapter` implementation, tests,
monitoring, safety boundaries, and report format. Its current validation uses
the controlled `DemoApiAdapter` and the contract-level `FakeAdapter`.

The repair skill requires an evidence-based classification before an edit. A
safe parser regression follows a redacted-fixture, failing-regression-test,
minimal-parser-change, passing-checks sequence. Access, session, CAPTCHA, and
unknown failures stop for human review instead of becoming parser changes.

## Daily Inspection Boundary

The daily workflow consumes a non-secret, read-only HTTPS health report. It
does not connect to a database, Redis, browser profile, or secret manager. The
report contains aggregate counters and safe snapshot counts only. When it finds
an actionable anomaly it may open or update a GitHub Issue; it cannot write
repository contents, merge, or deploy.

The runtime report publisher is intentionally out of scope because no approved
production source or production deployment exists. P7 verifies the deterministic
report parser, formatter, workflow permissions, and fixture contract locally.
