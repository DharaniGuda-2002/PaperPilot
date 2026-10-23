# ADR 0007: Deterministic comparison and evidence-backed reports

- Status: accepted
- Date: 2026-10-23

## Problems

1. Turn per-paper evidence into an answer to the research question without
   ranking methods on results that were measured differently.
2. Never state something the stored evidence does not support. The project
   budget is $0, so there is no hosted language model to write prose, and an
   unverified generator would be a fabrication risk anyway.
3. Show a busy reader the answer quickly and a careful reader every source.

## Decisions

**Comparison is rules, not judgement** (`app/comparison/rules.py`, compare-v3).
- Only verified evidence and absence records are used.
- Two results are comparable only when metric, dataset, and evaluation protocol
  are all known and equal. Extraction does not tie a value to a dataset, so a
  value inherits a dataset (or protocol) only when its paper reports exactly
  one. Everything else goes to `not_comparable`, with its reasons.
- Percentages and ratios share one 0–1 scale. Values without a unit are never
  normalized or compared.
- Author claims ("A outperforms B") are read from one clause. Claims in
  opposite directions across papers are listed as conflicts.
- Nothing ranks methods across groups. Within a group, values are shown as
  reported, not reproduced.

**Reports are assembled, not generated** (`app/reports/builder.py`, report-v1).
Every sentence comes from a template filled with counts, names, and evidence
ids. There is no free text. Findings:
- claim families, prioritized when they involve the question's methods;
- groups of comparable results;
- caveats: comparability, missing results, partial coverage, and the authors'
  stated limitations.

The 3–5 most informative findings are kept and cross-linked. The bottom line
answers the question only from these findings. It always ends with: "This
summarizes reported evidence; it does not establish which method is better."

**Published strength definitions, not model confidence.**
- *Strong*: 3 or more full-text papers support it, and none reports the opposite.
- *Moderate*: 2 papers support it.
- *Limited*: 1 paper, or abstracts only.
- *Insufficient*: nothing checkable.

Any conflicting paper lowers the level by one. The definitions are part of
every report, and the UI shows them next to each label.

**One study counts once.** Before scoring, a preprint and its published
version (same normalized title, different DOIs) are merged. The version read in
full is kept. The merge count is shown in the report scope.

**Immutable, versioned reports.** Each build adds a row to
`investigation_reports` (unique per investigation and version). The row
records the extraction, validation, comparison, and report versions.
`python -m app.ops.reports rebuild <id>` makes a new version after a rules
change; old versions are kept.

**Pipeline end.** The report worker (group `report-workers`, api image) handles
`evidence.extracted`. It builds the report only when every per-paper task is
terminal. It then sets the investigation to `completed`, or to
`partially_completed` when a paper failed or had no text. A `build_report` task
with a unique key makes the build idempotent under redelivery.

**Progressive disclosure in the UI.**
- Level 1: bottom line, strength, scope, and limits.
- Level 2: findings expand in place. A caveat stays visible while its
  finding is collapsed.
- Level 3: the evidence inspector, a native `<dialog>` showing the exact
  quotation, page, document source, extraction and retrieval provenance, and
  validation checks.

The comparison matrix and source list are separate tabs, addressable with
`?view=`.

## Consequences

- Reports are reproducible and auditable: the same evidence and versions give
  the same report.
- They are also terse and sometimes awkward. A template cannot summarize
  nuance, and the report says "not found" far more often than a human reviewer
  would. Rule extraction recall is low (see [evaluation.md](../evaluation.md)),
  so reports understate what papers contain. They do not overstate it.
- Few results are comparable in practice: on the real RAG investigation, 0 of 10
  extracted results had a single known dataset, protocol, and unit. This is
  reported as a finding, not hidden.
- The report worker must not import ML packages, so it can run in the 331 MB
  api image. A test runs each api-image entry point with PyMuPDF, torch, and
  sentence-transformers blocked.

## Alternatives considered

- **LLM-written summaries.** Rejected: it would need a paid API or a local model
  far beyond the free-tier resources, and it could state things no quotation
  supports. It could be added later as a draft that cites only stored evidence
  ids and is checked against them.
- **Ranking methods by normalized value across datasets.** Rejected: it compares
  numbers measured under different conditions.
- **A score from 0 to 1 for confidence.** Rejected: it implies precision the
  method does not have. The four labels are defined by counting checkable sources.
