# ADR 0005: OpenAlex as the metadata provider, with a Postgres search cache

- Status: accepted
- Date: 2026-10-23

## Problem

PaperPilot needs paper metadata (title, authors, venue, year, abstract,
open-access links) for a research question. The source must be free, legally
reusable, and broad across fields. Its usage limits must not be exhausted by a
public demo.

## Alternatives

1. **Semantic Scholar API.** Good coverage of CS. Its key and terms suit
   research use, but its abstracts and some fields carry license restrictions.
2. **arXiv API.** Free, but limited to preprints in a few fields.
3. **OpenAlex.** Broad coverage of more than 250M works, CC0 data,
   open-access locations included.

## Decision

OpenAlex, accessed through a small `PaperProvider` protocol so another
provider can be added or swapped in tests.

Current OpenAlex terms (checked 2026-10-22 against live response headers):
usage is billed per request. Requests without a key share **$0.10/day per
outbound IP**, and a free key gives **$1/day**. A search costs **$0.001**, so
that is about 100 searches/day without a key and about 1,000 with one. The
per-second limit is 10 without a key and 30 with one. Both limits answer 429.

Protections, in order:

1. **Search cache in Postgres** (24 h). Repeated searches cost nothing.
2. **Daily provider-call cap** (default 500), counted from cache rows. It
   stays below the keyed budget, and cached searches keep working once it is
   reached.
3. **Per-client search rate limit** (default 20/min per IP).
4. **Client behavior:** requests are spaced at least 200 ms apart. Short
   429s and 5xx responses are retried up to 3 attempts with backoff.
   `Retry-After` over 5 s means the budget is spent, so the request fails
   fast with 503. Other 4xx responses are not retried.
5. The API key goes in the `Authorization` header, never in URLs or logs.

The provider call runs outside any database transaction.

## Trade-offs

- Cached results can be up to 24 h stale. That is acceptable for literature
  search.
- The cap is per deployment, not per user; a heavy user can use up the day for
  everyone. Per-IP limits make that slower, not impossible.
- Without `OPENALEX_API_KEY`, a hosted deployment shares its budget with every
  other tenant on the same outbound IP and may hit 429 quickly.

## Verification

Unit tests use a recorded OpenAlex response and a mock transport for retries,
fail-fast, and headers. API tests use a fake provider for caching, the cap,
rate limits, and upsert idempotency. A manual live search through the local
stack returned real results: 0.48 s uncached, 0.006 s cached.
