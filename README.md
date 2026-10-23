# PaperPilot

An evidence-backed research investigation engine. Ask a technical research question;
PaperPilot finds relevant papers, extracts reported evidence with source passages,
flags experiments that cannot be fairly compared, and produces a traceable report.

> **Status: Milestone 3 (event pipeline).** Creating an investigation starts a Kafka
> pipeline (transactional outbox → dispatcher → discovery workers) that links relevant
> OpenAlex papers to it. Evidence extraction and reports are not built yet.
> The pipeline runs in the local Docker setup; the public demo has no workers.
> See [docs/roadmap.md](docs/roadmap.md).

**Live demo:** https://paperpilot-web-tfx4.onrender.com (free tier: first load after
idle can take about a minute). API docs: https://paperpilot-api-2ykf.onrender.com/docs

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
| http://localhost:8080 | Landing page; the app is at `/app` (nginx serves the SPA and proxies `/api`) |
| http://localhost:8000/docs | API reference (OpenAPI) |
| http://localhost:8000/health/ready | Readiness: 200 when the database answers, else 503 |

Stop with `docker compose down`. Add `-v` to also delete the database and Kafka volumes.

Pipeline operations:

```bash
docker compose up -d --scale discovery-worker=3        # more consumers in the group
docker compose logs -f discovery-worker outbox-dispatcher
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group discovery-workers   # partitions and lag
```

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
| Backend types | `mypy app tests` |
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
backend/    FastAPI app, workers (app/workers), event contracts (app/events),
            Alembic migrations, pytest suite
frontend/   React + TypeScript + Vite, design tokens in src/styles/tokens.css
docs/       architecture, ADRs, roadmap
scripts/    smoke test
```

## API (v1)

| Method | Path | Result |
|---|---|---|
| POST | `/api/v1/investigations` | 201 + `Location`; body `{"question": "..."}` (10–500 chars) |
| GET | `/api/v1/investigations?limit=20&offset=0` | Newest first; `limit` 1–100 |
| GET | `/api/v1/investigations/stats` | Total and count per status |
| GET | `/api/v1/investigations/{id}` | 200, or 404 if unknown |
| GET | `/api/v1/papers/search?q=...` | OpenAlex search; filters `from_year`, `to_year`, `open_access_only`, `sort` (`relevance`, `citations`, `newest`), `page`, `per_page` (≤25). Cached 24 h |
| GET | `/api/v1/papers/{id}` | Stored paper metadata with provenance |
| GET | `/api/v1/investigations/{id}/tasks` | Pipeline tasks: status, attempts, errors, results |
| GET | `/api/v1/investigations/{id}/papers` | Discovered papers in rank order |
| GET | `/api/v1/system/pipeline` | Outbox backlog and oldest pending age |
| GET | `/health/live`, `/health/ready` | Liveness / readiness |

## Known limitations

- The pipeline ends after discovery, so investigations stay `running` until
  evidence extraction exists. Retries via redelivery and dead-letter handling come in M4.
- Paper search depends on OpenAlex usage limits; see
  [ADR 0005](docs/adr/0005-openalex-provider-and-search-cache.md).
- No authentication. Creating investigations is rate limited per client and capped
  per day; see [docs/deployment.md](docs/deployment.md#public-demo-safeguards).
- The public demo runs on free tiers (Render + Neon) and sleeps when idle; the first
  request can take about a minute. Kafka and workers (from M3) will be local-only. Setup and limits: [docs/deployment.md](docs/deployment.md).
