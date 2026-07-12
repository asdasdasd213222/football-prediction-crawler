# P0-01 Repository Foundation Design

## Scope

Create the repository foundation for a Python 3.12 multi-site data collection
project. This task deliberately excludes collection, scheduling, adapters,
storage, credentials, and deployment behavior.

## Design

The project uses a standard `src` layout with a single empty package named
`multisite_crawler`. Packaging and development tooling are configured in
`pyproject.toml`, with no runtime dependencies. A small import smoke test keeps
the initial test suite executable without inventing application behavior.

Repository guidance, installation instructions, an environment-variable
template, Git ignore rules, and empty tracked directories establish the working
contract for later phases. The Compose file is configuration-only and the CI
workflow runs the required quality gates on Python 3.12; neither deploys nor
starts production services.

## Acceptance

The README installation path must work in a clean virtual environment. Ruff,
Mypy, Pytest, and `docker compose config` must all succeed. No file contains a
real credential; `.env.example` contains names and non-sensitive placeholders
only. `TODO.md` is updated only after these checks pass.
