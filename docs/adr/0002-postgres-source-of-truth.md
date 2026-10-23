# ADR 0002: PostgreSQL + pgvector as the single source of truth

- Status: accepted
- Date: 2026-10-22

## Problem

We need relational state (investigations, tasks, provenance), full-text search,
and vector similarity search. Each could use a different store.

## Alternatives

1. Postgres + a separate vector DB (Qdrant, Pinecone) + Elasticsearch.
   Three systems to run, back up, and keep consistent; Pinecone is paid.
2. **Postgres with pgvector and built-in full-text search.** One database,
   one transaction boundary, free.

## Decision

Option 2. Schema changes go through Alembic migrations only; the app never
calls `create_all()`. Kafka is a transport, never the only copy of state.

## Trade-offs

- pgvector HNSW is slower than a dedicated vector DB at very large scale. Our
  corpus per investigation is hundreds to thousands of chunks, far below where
  that matters.
- Postgres full-text ranking (`ts_rank`) is simpler than BM25. We measure
  retrieval Recall@K before deciding whether that matters.

## Verification

Migrations run upgrade → downgrade → upgrade from an empty database in CI.
