# Deployment

Two deployments exist:

| | Local (reference) | Public demo |
|---|---|---|
| How | `docker compose up --build -d --wait` | Render Blueprint (`render.yaml`) + Neon |
| Components | Everything, including Kafka, the outbox dispatcher, and discovery workers | Frontend, API, Postgres. Kafka and workers are local-only (see below) |
| Cost | $0 | $0 on free plans, no payment method required |

## Free-tier research (checked 2026-10-22)

Limits change often; re-check the linked pages before relying on them.

| Need | Option | Key free limits | Verdict |
|---|---|---|---|
| API | **Render free web service** | 512 MB RAM / 0.1 CPU; spins down after 15 min idle, ~1 min cold start; 750 instance-hours per workspace per month; ephemeral filesystem; single instance; no SSH | **Chosen.** Docker support, deploys from GitHub, Blueprint-as-code |
| API | Fly.io | No free tier for new users; card required | Rejected |
| API | Koyeb | Pricing page lists no free web-service tier (only a 1 GB free Postgres) | Rejected |
| Postgres | **Neon Free** | 1 GB storage per project; 100 CU-hours per project per month; scales to zero after 5 min idle; 5 GB egress per month; no card; pgvector included | **Chosen.** No expiry, pgvector ready for M5 |
| Postgres | Render free Postgres | 1 GB; **expires 30 days after creation**; one per workspace; no backups | Rejected: expiry |
| Postgres | Supabase Free | 500 MB; paused after 1 week inactive; 2 active projects | Rejected: smaller, pauses |
| Frontend | **Render static site** | Free; global CDN | **Chosen.** Same account and Blueprint as the API |
| Frontend | Cloudflare Pages | 500 builds per month, 20,000 files | Good alternative; would add a third account |
| Kafka + workers | Render background workers | Not offered on the free plan | Kafka and workers stay local-only unless a verified free option appears |

Sources: [Render free tier](https://render.com/docs/free),
[Render instance types](https://render.com/docs/compute-plans),
[Render Blueprint spec](https://render.com/docs/blueprint-spec),
[Neon pricing](https://neon.com/pricing), [Neon plans](https://neon.com/docs/introduction/plans),
[Supabase pricing](https://supabase.com/pricing), [Koyeb pricing](https://www.koyeb.com/pricing),
[Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/).

### Consequences you will notice

- **Investigations created on the public demo stay queued.** The API still writes
  the task and outbox event, but no dispatcher or worker runs there. After a
  minute the investigation page says so. Paper search works because it runs
  inside the API.

- **First request after 15 idle minutes takes about a minute** (Render spin-up), plus a
  short Neon wake-up. The frontend shows its normal loading state meanwhile.
- **The browser calls the API cross-origin** (`paperpilot-web` → `paperpilot-api`).
  The API allows only the frontend's origin via `CORS_ORIGINS`.
- **Migrations run at API startup** (`alembic upgrade head && uvicorn ...`). Safe because
  the free plan runs exactly one instance; with several instances, move migrations to a
  one-off pre-deploy step so they cannot race.

## Public demo safeguards

Implemented before the first public deploy:

- `POST /api/v1/investigations` is limited per client IP (`CREATE_RATE_LIMIT_PER_MINUTE`,
  default 5) and globally (`DAILY_INVESTIGATION_CAP`, default 200 per rolling 24 h).
  Both return 429 with `Retry-After`.
- Request bodies over 16 KB return 413.
- Paper search: 20 per minute per IP, a 24 h result cache, and a cap of 500 uncached
  OpenAlex calls per rolling 24 h (`DAILY_PROVIDER_CALL_CAP`). Past the cap, new searches
  return 503 and cached ones keep working.
- The per-IP limiter is in memory and keys on `CF-Connecting-IP` from Render's
  Cloudflare edge (`CLIENT_IP_HEADER`). A forged `X-Forwarded-For` does not reset it,
  which was verified on the live demo.
  It is still best-effort (per process, lost on restart); the global DB-backed cap is
  the real backstop for the 1 GB database.
- The demo runs no workers, so investigations stay queued and cost nothing beyond a row.
  Locally, each investigation is bounded to 25 papers, 25 MB per PDF, and capped retries.
  Full list of controls and gaps: [security.md](security.md).

## First-time setup (you do these; they need your accounts)

1. **Neon**: sign up at https://neon.com (GitHub login works, no card). Create a project
   named `paperpilot` in a US region. Copy the connection string (it starts with
   `postgresql://` and ends with `?sslmode=require`). Keep it out of git and chat.
2. **Render**: sign up at https://render.com with GitHub. Choose **New → Blueprint**,
   pick the `PaperPilot` repository, and confirm the two services from `render.yaml`.
3. When Render asks for `DATABASE_URL`, paste the Neon string. Apply.
4. **Optional, least-privilege database role.** In the Render shell of
   `paperpilot-api` (or locally with the owner URL exported as
   `MIGRATION_DATABASE_URL`), run
   `APP_DB_PASSWORD=<new password> python -m app.ops.runtime_role`.
   Then in Render set `MIGRATION_DATABASE_URL` to the owner string and change
   `DATABASE_URL` to the same string with user `paperpilot_app` and the new
   password. The start script migrates through `MIGRATION_DATABASE_URL`.
   Skipping this leaves the demo on the owner role, as documented in
   [security.md](security.md).
5. **OpenAlex key (recommended):** create a free key at https://openalex.org/settings/api
   and add it as `OPENALEX_API_KEY` in the `paperpilot-api` service's **Environment** tab.
   Without it, searches share a $0.10/day budget with every other service on Render's
   outbound IP and may fail with "provider unavailable".
5. Wait for both services to go live. If Render had to rename a service (name taken),
   update `CORS_ORIGINS` and `VITE_API_BASE_URL` in `render.yaml` to the real URLs.

## Verifying a deployment

```bash
curl -s https://paperpilot-api-2ykf.onrender.com/health/ready     # may take ~1 min if asleep
./scripts/smoke-test.sh https://paperpilot-web-tfx4.onrender.com https://paperpilot-api-2ykf.onrender.com
```

The smoke test creates one investigation. Record results in [roadmap.md](roadmap.md).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| API deploy fails at `alembic upgrade head` | Wrong or missing `DATABASE_URL` | Re-paste the Neon string in the service's Environment tab |
| Browser console shows a CORS error | `CORS_ORIGINS` does not match the frontend URL exactly | Set it to the frontend URL, no trailing slash |
| Frontend shows "Could not reach the PaperPilot API" | API asleep and request timed out, or wrong `VITE_API_BASE_URL` | Reload after a minute; check the build env var and redeploy the static site |
| 429 on create | Rate limit or daily cap reached | Expected; wait or raise the cap |
| Search says the provider is unavailable | OpenAlex budget spent (often keyless on a shared IP) or outage | Add `OPENALEX_API_KEY`; check API logs for `openalex error response` |
| Everything suspended mid-month | 750 free instance-hours used up | Wait for the next month; the local stack is unaffected |
| Browser console shows a Content-Security-Policy violation | The API URL changed, or a new external resource was added | Update `connect-src` in `render.yaml` (and `frontend/nginx.conf` locally) |

### Local stack

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker compose up` fails with "port is already allocated" | Another process uses 5433, 8000, 8080, or 9094 | Stop it, or change the host side of the port in `docker-compose.yml` |
| First `up --build` takes many minutes | The ml image downloads CPU-only torch and the embedding model (about 2.2 GB) | Wait once; later builds reuse the layers |
| Investigation stays `queued` | Kafka or the dispatcher is not running | `docker compose ps`; `docker compose logs outbox-dispatcher`; `python -m app.ops.metrics` shows the outbox backlog |
| Stuck at "Reading papers" for minutes | PDF downloads honor each host's crawl delay (arXiv: 3 s) | Expected for 25 papers; `docker compose logs -f document-worker` shows progress |
| Report says "Report not ready" | Some paper is still being processed, or a task failed permanently and is waiting for retries | The investigation page lists each task; dead letters: `python -m app.ops.dead_letters list` |
| Smoke test fails at "evidence extraction did not finish" | Live OpenAlex and PDF fetching take longer than the default 120 s | `EXPECT_PIPELINE=1 PIPELINE_TIMEOUT=600 ./scripts/smoke-test.sh` |
| `evaluation/run-gold.sh` says a paper has no stored full text | The gold papers have not been processed in this database | Run the gold set's question as an investigation first |
