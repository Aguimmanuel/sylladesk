# SyllaDesk — department-scale e-learning platform

Materials, assignments with dispute-proof receipts, timed randomized tests joined by code,
release-controlled scores. Built for one department, mobile-first, pages under 100KB.

Spec: `PRD-master.md` (full picture) · `PRD-v1.md` (live V1 spec) · `PROJECT-STRUCTURE.md` (code map) · `progress.md` (build journal).

## What to install

1. **VS Code** + the *Python* extension
2. **Git** — https://git-scm.com
3. **Docker Desktop** (runs PostgreSQL 18 locally; you can smoke-test without it, see below)
4. **uv** — your package manager of choice (non-standard but excellent): https://docs.astral.sh/uv/

## Quickstart (Docker, PostgreSQL 18 — the real setup)

    cp .env.example .env                # then edit SECRET_KEY
    docker compose -f docker/compose.yml up --build
    # app on http://localhost:8000 — create demo accounts:
    docker compose -f docker/compose.yml exec app python manage.py seed_demo

## Quickstart (uv, SQLite smoke-test only)

    uv venv
    uv pip install -r requirements.txt      # macOS/Linux: source .venv/bin/activate first; Windows: .venv\Scripts\activate
    uv run python manage.py migrate         # add: DATABASE_URL=sqlite:///var/dev.sqlite3 (PowerShell: $env:DATABASE_URL="...")
    uv run python manage.py seed_demo
    uv run python manage.py runserver

> SQLite is for a quick look only — development and production run PostgreSQL (PRD decision D-01).

## Tests

    uv run python manage.py test            # (or activate the venv and drop `uv run`)

## Ops

`scripts/backup.sh` + `scripts/restore.sh` (nightly offsite backups — FR-25) · `runbook.md` for procedures.
