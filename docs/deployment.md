# Deployment

Two deployments exist:

| | Local (reference) | Public demo |
|---|---|---|
| How | `docker compose up --build -d --wait` | Render Blueprint (`render.yaml`) + Neon |
| Components | Everything | Frontend, API, Postgres. Kafka and workers will stay local-only (see below) |
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
- The per-IP limiter is in memory and trusts the platform's `X-Forwarded-For`, so it is
  best-effort; the global DB-backed cap is the real backstop for the 1 GB database.
- No expensive processing exists yet. Before M2+ adds external API calls, the caps must
  also bound that work.

## First-time setup (you do these; they need your accounts)

1. **Neon**: sign up at https://neon.com (GitHub login works, no card). Create a project
   named `paperpilot` in a US region. Copy the connection string (it starts with
   `postgresql://` and ends with `?sslmode=require`). Keep it out of git and chat.
2. **Render**: sign up at https://render.com with GitHub. Choose **New → Blueprint**,
   pick the `PaperPilot` repository, and confirm the two services from `render.yaml`.
3. When Render asks for `DATABASE_URL`, paste the Neon string. Apply.
4. **OpenAlex key (recommended):** create a free key at https://openalex.org/settings/api
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
