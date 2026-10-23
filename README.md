# PaperPilot

An evidence-backed research investigation engine. Ask a technical research question;
PaperPilot finds relevant papers, extracts reported evidence with source passages,
flags experiments that cannot be fairly compared, and produces a traceable report.

> **Status: Milestone 1 (foundation).** You can create and browse investigations
> through a real API and database. Paper discovery, the Kafka pipeline, evidence
> extraction, and reports are not built yet. See [docs/roadmap.md](docs/roadmap.md).

PaperPilot evaluates *reported* evidence. It does not prove scientific reproducibility.

## Quick start (Docker)

Requires Docker with Compose v2.

```bash
cp .env.example .env        # optional; defaults work for local use
docker compose up --build -d --wait
./scripts/smoke-test.sh     # end-to-end check through the frontend proxy
```

| URL | What |
|---|---|
| http://localhost:8080 | Web app (nginx serves the SPA and proxies `/api`) |
| http://localhost:8000/docs | API reference (OpenAPI) |
| http://localhost:8000/health/ready | Readiness: 200 when the database answers, else 503 |

Stop with `docker compose down`. Add `-v` to also delete the database volume.

## Local development

```bash
cp .env.example .env                            # backend reads DATABASE_URL from it
docker compose up -d db                         # Postgres + pgvector on localhost:5433

cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:create_app --factory --reload  # http://localhost:8000

cd ../frontend
npm ci
npm run dev                                     # http://localhost:5173, proxies /api to :8000
```

## Checks

| Area | Command (run inside the folder) |
|---|---|
| Backend lint/format | `ruff check . && ruff format --check .` |
| Backend types | `mypy app` |
| Backend tests | `pytest` (needs the `db` container; uses a separate `paperpilot_test` database) |
| Frontend | `npm run typecheck && npm run lint && npm test && npm run build` |
| Color contrast | `npm run contrast` (WCAG 2.2 AA for every token pair the UI uses) |

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs all of these,
then builds the full Compose stack and runs the smoke test.

## Architecture

FastAPI modular monolith + PostgreSQL (with pgvector) as the single source of truth.
Background processing will run in separate worker processes coordinated through Kafka
with a transactional outbox. Details: [docs/architecture.md](docs/architecture.md) and
the decision records in [docs/adr/](docs/adr/).

```
backend/    FastAPI app, Alembic migrations, pytest suite
frontend/   React + TypeScript + Vite, design tokens in src/styles/tokens.css
docs/       architecture, ADRs, roadmap
scripts/    smoke test
```

## API (v1)

| Method | Path | Result |
|---|---|---|
| POST | `/api/v1/investigations` | 201 + `Location`; body `{"question": "..."}` (10–500 chars) |
| GET | `/api/v1/investigations?limit=20&offset=0` | Newest first; `limit` 1–100 |
| GET | `/api/v1/investigations/{id}` | 200, or 404 if unknown |
| GET | `/health/live`, `/health/ready` | Liveness / readiness |

## Known limitations

- No processing pipeline yet: investigations stay `queued`.
- No authentication, rate limiting, or quotas yet. Do not expose this build publicly
  beyond a demo; quotas are required before any expensive processing is added.
- Public deployment is not done yet; see [ADR 0004](docs/adr/0004-zero-cost-deployment.md).
