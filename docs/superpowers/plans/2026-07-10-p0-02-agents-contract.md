# P0-02 AGENTS Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define a concise, enforceable repository contract for safe and maintainable multi-site data collection development.

**Architecture:** `AGENTS.md` is the repository-wide policy layer. It defines stable boundaries and verification rules while site-specific policies belong in closer `AGENTS.md` files that may add, but never weaken, the root rules.

**Tech Stack:** Markdown, Python 3.12, Ruff, Mypy, Pytest, Docker Compose.

## Global Constraints

- Execute P0-02 only; do not implement collection, scheduling, adapters, storage, migrations, or deployment behavior.
- Do not record credentials, account data, cookies, tokens, or production environment values.
- A task is complete only after `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config` succeed.
- Update P0-02 checkboxes in `TODO.md` only after document review and all checks pass.

---

### Task 1: Replace Bootstrap Guidance with the Repository Contract

**Files:**
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: P0-02 requirements in `TODO.md` and existing Python tooling commands.
- Produces: root-level policy read by every future repository task.

- [ ] **Step 1: State project objective, non-goals, and directory ownership**

Use imperative rules covering `src/`, `tests/`, `configs/`, `scripts/`, and `docs/`. State that the system collects authorized public or explicitly permitted data and that this task does not authorize bypassing access controls or deploying production changes.

- [ ] **Step 2: Define architecture and runtime rules**

Require one adapter per website, site-neutral scheduler and storage layers, idempotent tasks, ordinary HTTP or documented feeds before browser automation, and redacted failure snapshots. Require exceptions to retain context and propagate through an explicit failure path.

- [ ] **Step 3: Define safety, migration, and Definition of Done rules**

Forbid credentials in source control and logs. Require reversible Alembic upgrade/downgrade/upgrade verification when database work is introduced. Require the five existing quality commands, documentation updates for behavior changes, and human review before production deployment. State that nested `AGENTS.md` files may add stricter rules only.

### Task 2: Verify the Contract and Record Completion

**Files:**
- Modify: `TODO.md`

**Interfaces:**
- Consumes: the completed `AGENTS.md` and all quality-gate results.
- Produces: P0-02 completion state.

- [ ] **Step 1: Inspect contract coverage and sensitive-content patterns**

Run: `rg -n "one adapter|idempotent|HTTP|exception|Alembic|Definition of Done|AGENTS.md" AGENTS.md`

Expected: every required policy topic appears in the root contract.

Run: `rg -n -i "(api[_-]?key|secret|token|password|cookie)\s*[:=]\s*[^\s#]+" AGENTS.md`

Expected: no credential-like assignment appears.

- [ ] **Step 2: Run quality gates**

Run: `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config`.

Expected: every command exits with status `0`.

- [ ] **Step 3: Check P0-02 only after all acceptance evidence exists**

Change the P0-02 implementation, acceptance, and execution-order checkboxes in `TODO.md` from `[ ]` to `[x]`.
