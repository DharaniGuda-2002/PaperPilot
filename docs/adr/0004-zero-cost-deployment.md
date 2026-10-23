# ADR 0004: $0 deployment strategy

- Status: proposed (provider limits not yet verified)
- Date: 2026-10-22

## Problem

The project must be deployable for $0. Free tiers often sleep idle services,
cap database size, and rarely offer a persistent Kafka broker or always-on
background workers.

## Decision

1. **Local is the reference deployment.** `docker compose up` runs the
   complete system (frontend, API, Postgres + pgvector, Kafka, workers,
   dispatcher). It must always work from a clean checkout.
2. **Public demo hosts only what free tiers verifiably support.** Candidates
   to evaluate when we deploy (none verified yet):
   - Frontend: static hosting (Cloudflare Pages, GitHub Pages, Netlify).
   - API: a free container web service (e.g. Render free tier; sleeps when idle).
   - Postgres + pgvector: a free managed Postgres (e.g. Neon, Supabase).
   - Kafka and workers: likely local-only; check current free Kafka offerings
     and their time/credit limits before relying on any.
3. Components that cannot be hosted reliably for free are documented as
   local-only. No paid service is added without explicit approval.
4. The public demo must cap expensive processing (quotas, rate limits) before
   any processing pipeline is exposed.

## Verification

Before each public deployment: read the provider's current limits, deploy,
run the smoke test against the public URL, and record results in
`docs/deployment.md`.
