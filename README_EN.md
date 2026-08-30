# Talos Vulnerability Management Platform

[简体中文](README.md) | **English**

Talos is named after the bronze giant of Greek mythology who guarded Crete — invulnerable everywhere except for a single weak point at his ankle. Security work is much the same: find and fix that one critical vulnerability.

Talos is a modern, full-lifecycle vulnerability management platform — a ground-up rewrite of the legacy internal platform "insight2" on FastAPI + Vue 3. It covers the complete workflow from vulnerability submission, triage and confirmation, remediation tracking and retesting, through to report delivery.

## Features

### Vulnerability Management

- **Full-lifecycle state machine**: Pending Review → Confirmed → Fixing → Retest → Completed, with a full operation trail; supports multiple retest rounds with conclusions linked to vulnerability states
- **CVSS 3.1 scoring**: an embedded calculator scores eight metrics in real time and syncs the risk severity accordingly; CVSS vectors are persisted
- **Vulnerability knowledge base**: curated templates for common vulnerability types, one-click apply in the submission form, auto backfill during report imports
- **Application & asset inventory**: many-to-many linkage between assets and vulnerabilities; public/intranet URLs feed tickets and reports

### Report Center

- **Word report import**: upload initial/retest Word reports against a fixed template; the backend parses them automatically (images included), and records are batch-created after preview confirmation. The import list supports batch linking to tickets and confirmed exports
- **Online report editing**: TipTap rich-text editor with tables/images/code blocks, autosave with optimistic locking, and one-click insertion of existing vulnerability sections
- **One-click export**: Word (docx) and PDF (via Gotenberg) share identical layouts; the table of contents is a TOC field that refreshes on open; exports run through a job queue with duplicate-export detection and export history
- **Automatic report metadata**: tested accounts, test period, participants, and tested-system URLs are resolved automatically via the ticket → asset chain

### Special-Purpose Tickets

- **Testing plans (penetration-test tickets)**: ticket IDs, tested systems, test types, and man-day tracking, linked to vulnerabilities and reports; tested-system URLs are pulled from the asset inventory
- **Remote testing / special campaigns / scan-baseline tickets**: disclosure handling, campaign paperwork, and host/web/baseline scan tickets each with their own workflows, managed alongside testing plans

### Insights & Administration

- **Security dashboard**: vulnerability trends, severity/status/type distribution, fix rate, and more, visualized with ECharts
- **RBAC**: JWT (access/refresh) authentication with idle sliding expiration on refresh tokens; role-permission model with directory-based permission management and menu/button-level control in the frontend
- **Notification channels**: WeCom/DingTalk webhooks plus SMTP email, subscribable to four event types — vulnerability created, ticket claimed, status transition, retest completed
- **Open API**: personal access tokens (PATs, plaintext shown once) with read-only endpoints (`/open/vulns`, `/open/stats`), rate-limited per token
- **Audit logs**: successful/failed logins (IP/UA) and sensitive operations are recorded uniformly and searchable

## Tech Stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic |
| Database / Queue | PostgreSQL 16 (SQLite for local development) · Redis · arq async task queue |
| Frontend | Vue 3 · TypeScript · Vite · Pinia · Element Plus · TailwindCSS · ECharts · TipTap 2 |
| Document Processing | python-docx (parsing) · htmldocx + pygments (export) · Gotenberg (PDF conversion) |
| Deployment | Docker Compose (api / worker / frontend / postgres / redis / gotenberg) |

## Quick Start (Docker Compose)

Prerequisites: Docker and the Docker Compose plugin installed on the server.

1. Prepare environment variables (`.env` is git-ignored — never commit it):

   ```bash
   cp .env.example .env
   # Edit .env and set at minimum:
   #   VP_SECRET_KEY     —— JWT signing key, >=32 random chars: openssl rand -hex 32
   #   POSTGRES_PASSWORD —— database password
   ```

   > Both values are strictly validated; startup is refused if they are missing.

2. Start everything:

   ```bash
   docker compose up -d --build
   ```

   Database schema, built-in roles/dictionaries, and the admin account are created automatically — no manual initialization required.

3. Retrieve the initial admin password (randomly generated and printed only once if `VP_INITIAL_ADMIN_PASSWORD` is unset; a password change is forced on first login):

   ```bash
   docker compose logs api | grep -i "初始密码"
   ```

4. Access:

   - Web UI: http://localhost:27012 (change the mapping under `ports` in `docker-compose.yml` as needed)
   - The frontend nginx proxies `/api` same-origin to the backend, so port 8000 usually needs no external exposure and no extra CORS setup
   - API docs are only available in debug mode (`VP_DEBUG=1`): `/api/docs`

> **Security notice**: in production keep `VP_DEBUG` off and use a strong random `VP_SECRET_KEY` and database password; if you explicitly set `VP_INITIAL_ADMIN_PASSWORD`, still change the admin password promptly after first login.

**Upgrade / backup / migration**: use `bash scripts/upgrade.sh` (backup → pull code → rebuild images → migrate database → restart), `bash scripts/backup.sh`, and `bash scripts/restore.sh backups/<timestamp>` respectively. See [docs/DEPLOY.md](docs/DEPLOY.md) for detailed procedures and troubleshooting.

## Local Development

One-command scripts (create the virtualenv and install dependencies automatically; SQLite + queue-free mode, no Postgres/Redis needed; built-in account fixed to `admin / admin123`):

```bash
# Windows
powershell -ExecutionPolicy Bypass -File .\dev.ps1

# Linux / macOS
bash dev.sh
```

Then open http://localhost:27014 (services bind to 0.0.0.0, externally reachable at http://<host-ip>:27014). API docs: http://localhost:27014/api/docs. Ctrl+C stops both frontend and backend. Override the default ports 27014 / 27015 with the `FRONTEND_PORT` / `BACKEND_PORT` environment variables (or the `-FrontendPort` / `-BackendPort` parameters of dev.ps1).

<details>
<summary>Manual steps</summary>

Backend (Postgres/Redis-free):

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
set VP_DATABASE_URL=sqlite+aiosqlite:///./dev.db
set VP_DISABLE_QUEUE=1
set VP_DEBUG=1
set VP_INITIAL_ADMIN_PASSWORD=admin123
.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 27015
```

Frontend (pnpm only):

```bash
cd frontend
pnpm install
pnpm run dev   # http://localhost:27014, proxies /api and /storage to 27015
```

</details>

Run tests:

```bash
cd backend
.venv/Scripts/python -m pytest          # backend pytest

cd frontend
pnpm test                               # frontend vitest
```

## PDF Conversion Service (Gotenberg)

`VP_GOTENBERG_URL` points to the DOCX→PDF conversion service, used by "report PDF export" and "imported-file online preview" (backend default `http://localhost:3000`; all settings use the `VP_` prefix and can go into `.env` or environment variables).

| Environment | Configuration |
| --- | --- |
| Docker Compose | A `gotenberg/gotenberg:8` service is included and the URL is injected — works out of the box |
| Local development | Optional: `docker run --rm -p 3000:3000 gotenberg/gotenberg:8` (the default value already points here) |

Without Gotenberg, only PDF preview/export returns 502 with a "conversion service unavailable" notice; all other features are unaffected. In production, keep Gotenberg on the internal network and do not expose port 3000.

## Project Layout

```
├── backend/
│   ├── app/
│   │   ├── api/v1/        # Routes: auth / users / vulns / assets / reports / imports / dashboard /
│   │   │                  #   knowledge / remote_testing / testing_plan / spring_action / nonpen /
│   │   │                  #   audit / notify / pats / open_api / misc
│   │   ├── core/          # Config, security, DI, pagination & sorting, filter engine, rate limiting,
│   │   │                  #   sanitization, timezones, xlsx
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schema package (split by domain, re-exported via __init__.py)
│   │   ├── services/      # State machine, docx parsing, import ingestion, report building,
│   │   │                  #   export, stats aggregation, audit, notifications
│   │   ├── constants.py   # Single source of truth for all enums/dictionaries and display colors
│   │   │                  #   (delivered to the frontend via /meta)
│   │   └── workers/       # arq background tasks (parsing, report export, notification dispatch)
│   ├── alembic/           # Database migrations
│   ├── scripts/           # Legacy data migration, DB adoption, seed data, and other ops scripts
│   └── tests/             # pytest tests
├── frontend/
│   └── src/{api, stores, router, views, components, composables, utils, layouts}
├── docs/                  # DEPLOY (ops manual) / RELEASE (changelog) / ROADMAP (evolution plan)
├── scripts/               # upgrade.sh / backup.sh / restore.sh / migrate.sh and other deploy scripts
├── dev.ps1 / dev.sh       # One-command local development scripts
└── docker-compose.yml
```

## Legacy Data Migration

To migrate data from the legacy insight2 (MySQL):

```bash
python backend/scripts/migrate_from_insight2.py --help
```

Plaintext passwords are not migrated; legacy users must reset their password on first login.

## Roadmap & Releases

- Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md)
- Versioning follows SemVer; the changelog in [docs/RELEASE.md](docs/RELEASE.md) is the single source of truth. Current version: **2.6.0**

## License

For learning and internal security management use only.
