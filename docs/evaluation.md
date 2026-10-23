# Evaluation

This file records how PaperPilot's outputs were checked, with sample sizes.
Nothing here is a benchmark score. The checks are small, manual, and
**preliminary**; a proper evaluation set comes in M6.

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

## Planned for M6

A small, manually reviewed set: questions with expected papers, and passages
with expected facts. With it: retrieval Recall@K, extraction precision and
recall per field, and passage validity, with sample sizes and annotator
noted.
