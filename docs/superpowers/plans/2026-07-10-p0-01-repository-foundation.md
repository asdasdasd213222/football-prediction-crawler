# P0-01 Repository Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Python 3.12 repository foundation that can be installed and checked in a clean environment.

**Architecture:** Keep application code to one importable, behavior-free package in a `src` layout. Centralize packaging, linting, type checking, and test settings in `pyproject.toml`; keep Compose and CI limited to validating this foundation.

**Tech Stack:** Python 3.12, setuptools, Ruff, Mypy, Pytest, Docker Compose, GitHub Actions.

## Global Constraints

- Implement P0-01 only; do not add crawling, scheduling, adapters, persistence, or deployment behavior.
- Require Python `>=3.12,<3.13`; introduce no runtime dependencies.
- Do not store account data, cookies, tokens, proxy passwords, database passwords, or real credentials.
- Required local checks are `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config`.
- Update P0-01 checkboxes in `TODO.md` only after every required check succeeds.

---

### Task 1: Create Tooling Configuration and a Failing Package Test

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/.gitkeep`
- Create: `tests/test_package.py`

**Interfaces:**
- Produces: `multisite_crawler.__version__: str`, initially expected to be `"0.1.0"`.

- [ ] **Step 1: Write the package contract test**

```python
from multisite_crawler import __version__


def test_package_exposes_initial_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Configure packaging, development checks, and build metadata**

```toml
[project]
name = "multisite-crawler"
version = "0.1.0"
requires-python = ">=3.12,<3.13"

[project.optional-dependencies]
dev = ["mypy>=1.11", "pytest>=8.3", "ruff>=0.6"]
```

Create the README referenced by project metadata and an empty `src` directory
before installing the editable package. Neither file defines application
behavior.

- [ ] **Step 3: Install development dependencies and verify the test fails**

Run: `python -m pip install -e ".[dev]"; pytest tests/test_package.py -q`

Expected: FAIL because `multisite_crawler` does not yet exist.

### Task 2: Implement the Minimal Importable Package

**Files:**
- Create: `src/multisite_crawler/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: the import and version assertion from `tests/test_package.py`.
- Produces: `__version__ = "0.1.0"`.

- [ ] **Step 1: Write the minimal package implementation**

```python
"""Foundation package for the multi-site data collection project."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Verify the package test passes**

Run: `pytest tests/test_package.py -q`

Expected: PASS with one passing test.

### Task 3: Add Repository Guidance and Execution Surfaces

**Files:**
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `compose.yaml`
- Create: `.github/workflows/ci.yml`
- Create: `configs/.gitkeep`
- Create: `scripts/.gitkeep`

**Interfaces:**
- Consumes: package name `multisite-crawler` and required local quality commands.
- Produces: documented setup, safe environment template, ignored local state, Compose configuration, and CI validation.

- [ ] **Step 1: Create documentation and safety files**

Document Python 3.12 virtual-environment setup and the five required checks in `README.md`. Keep `AGENTS.md` limited to bootstrap scope and direct future work to the next unfinished task. Ignore virtual environments, caches, coverage, build artefacts, local environment files, and secret-key file suffixes. Use only non-sensitive placeholder values in `.env.example`.

- [ ] **Step 2: Create Compose and CI validation**

Use a non-deploying Compose service with the public `python:3.12-slim` image. Use a GitHub Actions workflow on push and pull request that installs `.[dev]` on Python 3.12 and runs Ruff, Mypy, Pytest, and `docker compose config`.

- [ ] **Step 3: Initialize the Git repository**

Run: `git init`

Expected: a new local repository; no remote, branch protection, deployment, or commit is created by this task.

### Task 4: Verify Acceptance and Record Completion

**Files:**
- Modify: `TODO.md`

**Interfaces:**
- Consumes: successful results from the five required commands and a secret scan.
- Produces: checked P0-01 implementation, acceptance, and execution-order items.

- [ ] **Step 1: Run all mandatory checks**

Run: `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `docker compose config`.

Expected: every command exits with status `0`.

- [ ] **Step 2: Scan project content for credentials**

Run: `rg -n -i "(api[_-]?key|secret|token|password|cookie)\s*[:=]\s*[^\s#]+" --glob "!TODO.md" --glob "!docs/**" .`

Expected: no real credential values; environment-variable names and documented policy text are allowed.

- [ ] **Step 3: Mark P0-01 complete only after acceptance passes**

Change every P0-01 implementation and acceptance checkbox, plus the current execution-order entry for P0-01, from `[ ]` to `[x]`.
