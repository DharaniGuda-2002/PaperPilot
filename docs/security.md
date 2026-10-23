# Security Notes

What protects PaperPilot, where it is implemented, how it was checked, and
what is not covered. Last reviewed 2026-10-23 (M7).

## Threat model in brief

- **Anonymous public users** can call the API on the demo. Risks: flooding
  the 1 GB database, spending the OpenAlex budget, large request bodies.
- **Third-party content** reaches the system: paper metadata, PDF URLs, PDF
  text, and abstracts. Risks: server-side request forgery (SSRF) through
  fetched URLs, oversized or malformed files, and text that tries to instruct
  the system.
- **Secrets**: the Neon connection string and an optional OpenAlex key.

Out of scope: authentication and multi-tenant data separation. There are no
user accounts, and every investigation is public on purpose.

## Controls

| Area | Control | Where | Verified by |
|---|---|---|---|
| Request size | 16 KB limit, enforced by Content-Length and by counting streamed bytes (chunked uploads) | `app/core/http.py` | `test_limits.py`; live 413 via nginx and uvicorn for a 50 KB chunked body |
| Input validation | Pydantic schemas: question 10–500 chars, bounded paging, UUID path parameters | `app/*/schemas.py`, `app/api` | API tests |
| Rate limits | Create: 5/min per client. Search: 20/min per client. Global caps: 200 investigations and 500 uncached OpenAlex calls per rolling 24 h | `app/api`, `app/core/rate_limit.py` | `test_limits.py` |
| Client address | Taken from the entry the trusted proxy appended to `X-Forwarded-For` (`TRUSTED_PROXY_HOPS`), never the client-supplied one | `client_address()` | Regression test; local forged-header experiment: 5 × 201, then 429 |
| Processing bounds | At most 25 papers per investigation; PDFs at most 25 MB with a 30 s timeout; bounded retries, then dead letter | settings, `app/documents/fetch.py` | Worker tests |
| SSRF | http/https on ports 80/443 only; every redirect hop resolved and checked; private, loopback, link-local, CGNAT, and mapped addresses rejected; connected peer re-checked; `%PDF` magic required | `app/documents/fetch.py` ([ADR 0006](adr/0006-documents-retrieval-and-evidence.md)) | 39 fetch tests; live blocks of the metadata IP, localhost, and `127.0.0.1.nip.io` |
| Robots and terms | Open-access PDFs only; robots.txt; per-host crawl delay shared across workers | `app/documents` | Tests; M5 real run |
| Untrusted paper text | Never executed or used as instructions: extraction is deterministic regex rules, with no language model. Text is stored and displayed as data | `app/evidence`, React text rendering (no `dangerouslySetInnerHTML`) | Code search |
| External links | Only http(s) URLs from paper metadata become links, opened with `rel="noopener noreferrer"` | `frontend/src/lib/safeUrl.ts` | Unit tests |
| SQL | SQLAlchemy expressions and bound parameters only; no string-built SQL with input | all DB code | Review |
| CORS | Exact origin list (`CORS_ORIGINS`), GET/POST only, two allowed headers | `app/main.py` | Config tests |
| Headers (API) | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, CSP `default-src 'none'; frame-ancestors 'none'` (not on `/docs` and `/redoc`, which load Swagger UI from a CDN) | `app/core/http.py` | `test_limits.py`; curl |
| Headers (web) | Same-origin CSP with no inline scripts or styles, `X-Frame-Options: DENY`, `Permissions-Policy`, `nosniff`, `Referrer-Policy`. Render adds HSTS | `frontend/nginx.conf`, `render.yaml` | curl; browser console showed no CSP violations across the app's pages |
| Errors and logs | 500s return a generic body; logs are JSON with a correlation id; a caller-supplied request id is accepted only if it is a UUID; no bodies, secrets, or IP addresses are logged | `app/main.py`, `app/core/logging.py` | Tests; log review |
| Secrets | Only in the environment: Render dashboard `sync: false` values, local `.env` (git-ignored). `.env.example` holds placeholders | `.gitignore`, `render.yaml` | gitleaks over the full history: 49 commits, no leaks (also in CI) |
| Dependencies | Exact pins. CI runs `pip-audit` (api and ml requirements) and `npm audit --omit=dev` | `.github/workflows/ci.yml` | 2026-10-23: no known vulnerabilities in either |
| Containers | API and workers run as uid 10001; nginx runs unprivileged on 8080; Postgres, Kafka, and the API bind to 127.0.0.1 in Compose | Dockerfiles, `docker-compose.yml` | `docker compose ps` |
| Shutdown | Workers finish the current message on SIGTERM, then close; offsets are committed after the DB transaction | `app/workers/consumer.py` | Worker tests |

## Known gaps

- **Database role.** The API and workers connect as the database owner, both
  locally and on Neon, so least privilege is not applied in the database. The
  fix: a runtime role with only SELECT/INSERT/UPDATE/DELETE on the
  application tables, with migrations run under the owner role. It is
  documented, not built.
- **Per-client limits are in memory.** They reset when the process restarts
  and are per instance. The database-backed daily caps are the real
  backstop.
- **Render's proxy chain is not documented.** `TRUSTED_PROXY_HOPS=1` assumes
  Render appends one entry. A forged leftmost entry no longer resets the limit
  on the demo (see roadmap, M7 log). If Render ever adds a second, shared
  hop, clients would share one bucket. That would fail closed (more 429s), not
  open.
- **No authentication.** Anyone can create investigations within the caps
  and read all of them. This is acceptable for a demo of public research
  questions, not for private data.
- **Swagger UI** at `/docs` loads its assets from a CDN without a CSP.
- **Kafka** has no TLS or authentication. It is local-only and not exposed
  beyond 127.0.0.1.

## Reporting

Open a GitHub issue without exploit details, and ask for a private contact.
