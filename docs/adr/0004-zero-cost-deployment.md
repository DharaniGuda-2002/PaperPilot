# ADR 0004: $0 deployment strategy

- Status: accepted (limits checked 2026-10-22; see docs/deployment.md)
- Date: 2026-10-22

## Problem

The project must be deployable for $0. Free tiers often sleep idle services,
cap database size, and rarely offer a persistent Kafka broker or always-on
background workers.

## Decision

1. **Local is the reference deployment.** `docker compose up` runs the
   complete system (frontend, API, Postgres + pgvector, Kafka, workers,
   dispatcher). It must always work from a clean checkout.
2. **Public demo hosts only what free tiers verifiably support.** Chosen after
   checking current limits (comparison in `docs/deployment.md`):
   - Frontend: Render static site.
   - API: Render free Docker web service (sleeps after 15 min idle).
   - Postgres + pgvector: Neon Free (no expiry; Render's free Postgres expires
     after 30 days).
   - Kafka and workers: local-only; Render offers no free background workers.
3. Components that cannot be hosted reliably for free are documented as
   local-only. No paid service is added without explicit approval.
4. The public demo must cap expensive processing (quotas, rate limits) before
   any processing pipeline is exposed.

## Verification

Before each public deployment: read the provider's current limits, deploy,
run the smoke test against the public URL, and record results in
`docs/deployment.md`.
