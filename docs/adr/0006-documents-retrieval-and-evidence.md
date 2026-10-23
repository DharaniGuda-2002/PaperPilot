# ADR 0006: Document processing, hybrid retrieval, and rule-based evidence

- Status: accepted
- Date: 2026-10-23

## Problems

1. Get paper text legally and safely. URLs come from third-party metadata, so
   fetching them is a server-side request forgery (SSRF) risk.
2. Keep exact page references, so every extracted fact can point to a page.
3. Find the passages relevant to the research question in each paper.
4. Extract structured facts without inventing anything, at $0.

## Decisions

**Permitted text only.** A PDF is fetched only when OpenAlex marks the work open
access and lists a PDF URL. No authentication or paywall handling, ever.
Otherwise the abstract from OpenAlex is used and the document is labeled
`abstract`, with the reason full text is unavailable. Per-host throttling
respects source terms (arXiv asks for at most one request every 3 s).

**SSRF guard** (`app/documents/fetch.py`):
- http/https only; ports 80/443.
- Every redirect hop is resolved and validated, with at most 5 hops.
- The hostname is rejected if *any* resolved address is private, loopback,
  link-local, multicast, reserved, or unspecified, including IPv4-mapped IPv6.
- After connecting, the **actual peer address** is checked before the body is
  read, which closes the DNS-rebinding gap between validation and connection.
- 25 MB streaming cap, 30 s timeout, and the content must be a PDF (`%PDF`
  magic bytes).

**PyMuPDF for extraction**, one text block per page. Chunks never cross pages,
so a chunk's page number is exact. Chunks are about 900 characters, because
the embedding model reads at most 256 tokens.

License: PyMuPDF is **AGPL-3.0** (or a commercial license). This repository
is public. If the project gets an open-source license it must be
AGPL-compatible, or the extractor should be swapped for a permissive one
(pypdf, BSD). The `extractor` and `extractor_version` columns make that swap
traceable.

**Local embeddings:** `sentence-transformers/all-MiniLM-L6-v2` at a pinned
revision, on CPU, normalized, 384 dimensions, in a pgvector `vector(384)`
column. Each chunk stores `embedding_model` (`name@revision`). Changing the
model means re-embedding, and the version column shows which rows are stale.
Torch and PyMuPDF live in `requirements-ml.txt` and a separate image target, so
the API image (deployed on a 512 MB free instance) does not carry them.

**Hybrid retrieval:**
- Postgres full-text search: `websearch_to_tsquery`, `ts_rank_cd`, GIN index.
- Vector search: cosine distance, HNSW index.
- Fused with Reciprocal Rank Fusion: score = Σ 1/(60 + rank).
- Each candidate records which method(s) found it and its rank in each. The
  weights are configurable. Quality is measured before tuning (M6 evaluation).

**Rule-based evidence extraction, not an LLM, for now.**
- Rules: regular expressions and small lexicons for metrics with values,
  datasets, methods, baselines, splits and protocols, limitations, and code
  availability.
- Each fact carries the **exact sentence** it came from (`passage_kind =
  quotation`), its page, the chunk, the retrieval provenance, and
  `extraction_method = rules`, `extraction_version = rules-v1`.
- Fields with nothing found are recorded explicitly: `not_found` when full
  text was searched, `unavailable` when only an abstract existed. Missing text
  is never treated as evidence that something is false.
- An optional local LLM extractor can be added later behind the same
  interface. Its output would go through the same validation.

**Deterministic validation** runs for every record and is stored as an
append-only history (`evidence_validations`):
- the passage appears verbatim in the stored chunk text;
- the page number lies within the document;
- every number in the value appears in the passage.

A record that fails any check is `rejected` and is kept for transparency, not
deleted.

**Pipeline:**
- `paper.discovered` → document worker (per paper, cached across
  investigations) → `document.processed` (keyed by paper).
- Evidence worker: retrieval, extraction, and validation in one transaction →
  `evidence.extracted` (keyed by investigation, for the M6 report stage).
- Validation is fast and deterministic, so it runs inside the evidence worker
  rather than in a separate one.

## Trade-offs

- Rules miss facts phrased in unusual ways, and lexicons favor the
  fraud-detection and ML vocabulary of the example questions. Recall is
  measured in M6 rather than assumed.
- Full text is limited to open-access PDFs. Many papers fall back to
  abstracts, and reports must say so.
- One more image to build (the ML target), and torch adds about 600 MB.
