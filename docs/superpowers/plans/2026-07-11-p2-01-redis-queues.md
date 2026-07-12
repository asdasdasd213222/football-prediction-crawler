# P2-01 Redis And Task Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide Redis-backed Celery workers with safe delivery, separate HTTP/browser queues, retries, timeouts, and queue-depth metrics.

**Architecture:** A site-neutral queue module owns Celery configuration and Redis metrics; task wrappers only route non-sensitive source identifiers. Compose runs Redis and separate queue workers; PostgreSQL remains the business system of record.

**Tech Stack:** Python 3.12, Celery 5, Redis 7, Docker Compose, Pytest, Ruff, Mypy.

## Global Constraints

- Implement P2-01 only; do not add scheduling, website-specific adapters, real-site access, credentials, or deployment.
- Redis is the broker only; PostgreSQL remains the durable business record.
- Use late acknowledgement, reject-on-worker-lost, prefetch one, JSON serialization, three retries, 60-second soft and 75-second hard limits.
- Maintain `http` and `browser` queue separation and typed queue-depth metrics.
- Run repository quality checks and an approved local Docker integration check before marking P2-01 complete.

### Task 1: Queue Contract And Tests

**Files:** `tests/test_queueing.py`, `src/multisite_crawler/queueing.py`, `src/multisite_crawler/tasks.py`, `pyproject.toml`.

- [ ] Write failing tests for explicit route selection, retry settings, and typed queue metrics.
- [ ] Run the focused tests and verify missing-module failure.
- [ ] Add Celery and Redis dependencies; implement a broker-only app with queue declarations, explicit routes, JSON serializers, late acknowledgement, reject-on-worker-lost, prefetch one, retry/time-limit defaults, and `queue_depths(redis_client)`.
- [ ] Run focused unit tests until green.

### Task 2: Compose Runtime

**Files:** `compose.yaml`, `.env.example`, `README.md`.

- [ ] Add failing Compose/runtime assertions where practical.
- [ ] Add Redis with a named local volume, health check, and non-secret environment variable names only.
- [ ] Add `worker-http` and `worker-browser` services, each constrained to its own queue and configured for warm shutdown.
- [ ] Document local-only runtime verification, queue roles, and no-result-backend policy.

### Task 3: Integration Acceptance

**Files:** `tests/test_queueing.py`, `TODO.md` only after all checks pass.

- [ ] Start local Redis/workers through Compose and prove each task routes to its intended queue.
- [ ] Verify Redis restart recovery and worker-loss redelivery with an idempotent test task.
- [ ] Verify retries do not duplicate the recorded task effect and queue-depth metrics remain separated.
- [ ] Run `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, `docker compose config`, and the local Docker integration check.
- [ ] Mark only P2-01 delivery, acceptance, and execution-list checkboxes after all evidence is green.

## Self-Review

The plan covers every P2-01 delivery and acceptance item while leaving P2-02 scheduling untouched. The module names and runtime configuration are site-neutral, and no placeholder endpoints or credentials are introduced.
