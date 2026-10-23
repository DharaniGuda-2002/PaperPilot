# Evaluation

This file records how PaperPilot's outputs were checked, with sample sizes.
Nothing here is a benchmark score. The checks are small and manual. The M6 gold
set is the first repeatable measurement, and it is still small: read the sample
sizes before the percentages.

## M5 real-run review (2026-10-23)

**Run:** "Does retrieval-augmented generation reduce hallucination in
open-domain question answering?", live OpenAlex, local stack, real embedding
model.

| Stage | Result |
|---|---|
| Discovery | 25 papers linked |
| Documents | 17 open-access full texts; 7 abstracts only (3 publisher 403s, 2 HTML pages instead of PDFs, 2 with no PDF link); 1 paper with no text at all |
| Time | all 25 papers documented and evidence-extracted 122 s after creation (one worker of each kind) |
| Politeness | requests went to 11 hosts and respected each host's robots.txt crawl delay; no deferrals were needed at this volume |

### Page references against original PDFs

**Method:** for 5 evidence records from 5 different full-text papers (4
hosts; result, baseline, code, and limitation fields), the PDF was
downloaded again and the passage was searched for on the cited page of the
*original* file. Our stored text was not used, since checking against it
would be circular.

**Result:** 5 of 5 passages found on the cited page.

**Limitations:** 5 records; one passage per paper; whitespace and
punctuation were ignored in the comparison.

### Extraction precision, metric results (rules-v2)

**Method:** every `metric_result` record in the run with a verified quote
(10 records) was read by the developer's assistant (not a domain expert)
against its passage.

| Check | Correct | Notes |
|---|---|---|
| Value and metric match the passage | 9 / 10 | 1 false positive: a hyperparameter table ("dropout 0.1, precision 4bit") read as "precision 0.1" |
| Credited to the right method | 7 / 10 | 1 wrong (SelfCheckGPT credited to "GPT"); 2 without a method because "Llama-2-13B" was not recognized |
| Duplicate records | 2 pairs | the same work appeared twice in OpenAlex results; discovery now links each work once (DOI / normalized title) |

### rules-v1 → rules-v2 on the same 25 papers

| Field | v1 records | v2 records | Why it changed |
|---|---|---|---|
| metric_result (quote verified) | 32 | 10 reported + 2 uncertain | v1 read numbers inside names (GPT-3.5, Recall@15) and changes ("improvements of 1%") as results |
| metric_result rejected | 25 | 0 | v1 rejected unit-less values; v2 records them as uncertain, quote verified |
| method | 11 | 94 | lexicon extended with retrieval and LLM names |
| baseline | 2 | 21 | follows from the larger method lexicon |
| dataset | 25 | 22 | plain words ("Benchmark", "One") no longer accepted |

v2 may have lost some true results that v1 found by accident. The 32
verified v1 values were not all reviewed one by one, so v1's precision and
v2's recall are **not measured**. Measuring them is M6 work.

### Known weaknesses

- Lexicons favor ML and fraud-detection vocabulary. Methods in other fields
  are mostly missed (shown as `not_found`, never as absent).
- Tables flattened into text can still yield wrong values when a row has
  fewer than 8 numbers.
- Method credit uses the nearest preceding mention and can be wrong when
  several methods share a sentence.
- Splits and protocols were found in only 2 of 17 full texts; most papers
  phrase them in ways the rules do not catch.

## M6 gold set: rag-hallucination-v1 (2026-10-23)

**What it is:** 84 facts from 5 open-access papers of the real RAG investigation:

| Paper | Pages | Gold facts |
|---|---|---|
| RAG for drug-related QA (Research Square preprint) | 6 | 16 |
| Reducing hallucination in structured outputs via RAG (NAACL Industry 2024) | 11 | 13 |
| REAR (EMNLP 2024) | 14 | 16 |
| RAGTruth (ACL 2024) | 17 | 21 |
| RAG for domain-specific QA (arXiv 2404.14760) | 8 | 18 |

**Annotator:** the AI coding assistant, not a domain expert. Every page of each
paper's stored text was read before any extraction output was looked at.
**Review:** reviewed and approved as annotated by the project owner
(DharaniGuda-2002) on 2026-10-23. The owner reviewed a per-paper walkthrough of
every fact and verdict, with the judgement calls below flagged. No annotation
changed, so the numbers are the same as before review. One annotator plus one
reviewer is still a small basis; read the sample sizes before the percentages.

**Judgement calls (approved as annotated):**
- **Scope:** baselines named only in table rows count, but results that appear
  only in tables do not.
- **Matching:** `split`, `code_availability`, and `limitation` match on the
  anchor's chunk, not the exact sentence.
- **Paper 1:**
  - Derived results count as facts: the 74.3% relative reduction and the
    pp improvements.
  - The limitations list is one fact.
  - The baseline's aliases accept "Llama 3.2" and "large language models".
- **Paper 2:**
  - The internal "Human Eval" and OOD1–5 splits count as datasets.
  - GTR-T5, a retriever baseline, counts as a baseline.
  - The bounds "as high as 21%" and "less than 7.5% / 4.5%" count as results.
  - The ethics-section statement counts as a limitation.
- **REAR:** Chain-of-Note counts as a baseline, although it is compared only on
  efficiency.
- **RAGTruth:**
  - MS MARCO, Yelp, and CNN/Daily Mail count as datasets, although they are
    used to generate responses.
  - The dataset repository link counts as code availability.
  - Annotator agreement (91.8%, 78.8%) is not counted as a result.
- **Paper 5:**
  - 11 table-row baselines count, so this paper makes up 41% of all baseline
    facts.
  - ChatGPT counts as a baseline, although the comparison is qualitative.
- **Verdicts:** all 9 unmatched records are incorrect, including the borderline
  "future work" record from REAR.

**What counts as a fact** (full guidelines in the gold file):
- **dataset** and **baseline**: what the paper's own experiments use, not
  related-work mentions;
- **split**: how evaluation was done;
- **metric_result**: numbers stated in prose; table-only values are out of
  scope because flattened tables cannot be annotated reliably;
- **code_availability**: a statement that code or released artifacts exist;
- **limitation**: limitations the authors state about their own work.

`method` is not annotated.

**How facts are stored:** each fact carries short verbatim anchors (under 15
words) that locate it in the stored text, not the passage itself.

**How it is scored** (`evaluation/run-gold.sh`, read-only):
- Retrieval and extraction are re-run on the stored papers.
- An extracted record that matches no gold fact needs a recorded verdict in
  `rag-hallucination-v1.judgements.json`. Unjudged records are reported and
  never counted. All 9 unmatched records in this run were judged.

Raw output: [evaluation/results/rag-hallucination-v1.json](../evaluation/results/rag-hallucination-v1.json).

### Retrieval (n = 84 facts)

For each fact, the pipeline's query for that field runs against that one paper.
A hit means a chunk containing the fact's anchor is in the top K.

| Retriever | @1 | @3 | @5 | @8 |
|---|---|---|---|---|
| Full-text search only | 0.119 | 0.405 | 0.595 | 0.619 |
| Vector only (MiniLM) | 0.155 | 0.393 | 0.476 | **0.690** |
| Hybrid RRF (used by the pipeline) | 0.155 | **0.440** | 0.512 | 0.583 |

**Pipeline coverage: 0.929.** The extractor receives the union of 7 queries (the
question plus one per field, top 8 each). For 78 of 84 facts, a chunk containing
the fact reaches the extractor.

Readings:
- Per query, hybrid is not better than either method alone at K = 8 (49 vs 52
  and 58 facts). RRF keeps chunks found by both lists, but cuts chunks ranked
  highly by only one.
- The union over queries hides this: retrieval is not what limits extraction.
- Weakest fields for hybrid@8: baseline (10 of 27) and limitation (3 of 7).
  A likely cause: many baselines appear only in table rows, which the
  "baselines compared with…" query does not resemble. This was not measured.
- With 5 papers and 84 facts, a difference of 3–4 facts is within noise. The
  ranking of the three methods is not established.

### Extraction (rules-v2, n = 84 gold facts, 17 extracted records)

| Field | Gold | Found | Recall | Extracted | Correct | Precision |
|---|---|---|---|---|---|---|
| dataset | 14 | 1 | 0.07 | 2 | 1 | 0.50 |
| baseline | 27 | 0 | 0.00 | 5 | 0 | 0.00 |
| split | 10 | 0 | 0.00 | 0 | 0 | – |
| metric_result (prose) | 23 | 4 | 0.17 | 4 | 4 | 1.00 |
| code_availability | 3 | 2 | 0.67 | 2 | 2 | 1.00 |
| limitation | 7 | 1 | 0.14 | 4 | 1 | 0.25 |
| **all** | **84** | **8** | **0.10** | **17** | **8** | **0.47** |

**Passage validity:** 17 of 17 records were verified: each quotation was found
in the stored text on the cited page, and numbers matched the passage. In M5,
5 of 5 cited pages were confirmed against the original PDFs. Passage validity
says the quote is real; it does not say the extracted value is right. Precision
measures that.

**Why recall is low** (diagnosed; the rules were not tuned on this set, so the
set stays a fair test):
- **Dataset.** The lexicon knows only fraud-detection datasets. The generic
  pattern needs the form "<Name> dataset". REAR's "Natural Questions (NQ) …
  TriviaQA … SQuAD" matches neither.
- **Baseline.** The rules take the nearest known method name near a cue word.
  The method lexicon misses most of the names here (SelfCheckGPT, LMvLM,
  GTR-T5, CodeLlama). When a cue fires, the wrong token is often taken: "RAG",
  "GPT", "CNN".
- **Split.** The patterns cover k-fold cross-validation, split ratios ("6:2:2"),
  training percentages, and temporal splits. These papers state protocols in
  words ("we follow the test split in prior work").
- **Metric results.** "Hallucination rate" and "faithfulness" are not in the
  metric lexicon. "Factual Accuracy from 0.54 to 0.89" is missed because "from …
  to" is not a supported connector between metric and value.
- **Limitation.** The cue words also fire on statements about other systems
  ("ChatGPT fails to…", "a limitation of generative AI").

**What this means for reports:**
- Reports built from rules-v2 evidence understate what papers contain. This
  is why the real investigation's report says most results are not comparable.
- Precision for numeric results and code links is high (4 of 4, 2 of 2), but
  the sample is far too small to quote as a rate.
- Name fields (dataset, baseline) are where wrong records come from.

**Limits of this evaluation:**
- 5 papers on one topic, chosen as the shortest full texts in the run.
- One annotator (not a domain expert) and one reviewer; the reviewer approved
  the annotations without changes.
- Table values are excluded.
- `split`, `code_availability`, and `limitation` match on the anchor's chunk,
  which is lenient: another sentence in the same chunk would count.
- Discovery (which papers OpenAlex returns) is not evaluated: there is no
  expected-paper list.
