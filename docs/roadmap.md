# Roadmap and Progress

Each milestone is finished and verified before the next starts.

## Checklist

- [x] M0 — Repository inspection, architecture, ADRs, acceptance criteria
- [ ] M1 — Application foundation (in progress; public deployment pending)
- [ ] M2 — Paper discovery (OpenAlex)
- [ ] M3 — Kafka pipeline (outbox, dispatcher, first idempotent consumer)
- [ ] M4 — Distributed reliability (retries, DLQ, recovery, throughput)
- [ ] M5 — Retrieval and evidence (PDFs, embeddings, hybrid search, extraction)
- [ ] M6 — Comparison and reports (rules, progressive-disclosure report UI)
- [ ] M7 — Hardening and final deployment

## M1 acceptance criteria

1. `docker compose up --build` from a clean checkout starts Postgres
   (pgvector image), runs migrations once, starts the API and the frontend;
   all services report healthy.
2. `GET /health/live` returns 200. `GET /health/ready` returns 200 when the
   database is reachable and 503 when it is not.
3. `POST /api/v1/investigations` with a valid question returns 201 and a
   `Location` header; the row is persisted with status `queued`.
4. Invalid questions (too short, too long, blank, extra fields) return 422.
5. `GET /api/v1/investigations` lists newest first with `limit`/`offset`
   (max limit 100). `GET /api/v1/investigations/{id}` returns 404 for
   unknown IDs.
6. Alembic upgrade → downgrade → upgrade works on an empty database.
7. The dashboard lets a user submit a question and see it in Recent
   Investigations, backed by the real API (no fixtures). The investigation
   page shows real status and states plainly that processing is not built yet.
8. Frontend uses the design tokens; no hardcoded hex colors in components;
   keyboard focus visible; status shown as text, not color alone.
9. Backend: ruff, mypy, pytest pass. Frontend: typecheck, lint, tests, build
   pass. A GitHub Actions workflow runs the same checks.
10. Public deployment: deferred until a GitHub remote and hosting accounts
    exist (see ADR 0004). Requires your approval to create.

## Verification commands (M1)

```bash
docker compose up --build -d
docker compose ps
curl -s localhost:8000/health/ready
curl -s -X POST localhost:8000/api/v1/investigations -H 'content-type: application/json' \
  -d '{"question":"Do graph neural networks outperform gradient boosting for fraud detection?"}'
cd backend && ruff check . && ruff format --check . && mypy app && pytest
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```
