// Mirrors backend/app/reports/schemas.py and app/comparison/rules.py.

export type Strength = 'strong' | 'moderate' | 'limited' | 'insufficient'
export type FindingKind = 'claim' | 'comparison' | 'caveat'

export interface StudySupport {
  paper_id: string
  title: string
  year: number | null
  content_kind: string
  detail: string
  evidence_ids: string[]
}

export interface Finding {
  id: string
  kind: FindingKind
  title: string
  summary: string
  strength: Strength | null
  strength_reason: string | null
  supporting: StudySupport[]
  conflicting: StudySupport[]
  warnings: string[]
  related: string[]
}

export interface ResultCell {
  evidence_id: string
  metric: string
  value: number
  unit: string | null
  normalized: number | null
  method: string | null
  page: number | null
}

export interface MatrixRow {
  paper_id: string
  title: string
  year: number | null
  content_kind: string
  methods: string[]
  proposed_methods: string[]
  datasets: string[]
  protocols: string[]
  baselines: string[]
  results: ResultCell[]
  missing_fields: string[]
  warnings: string[]
}

export interface ComparableGroup {
  metric: string
  dataset: string
  protocol: string
  members: { paper_id: string; evidence_id: string; method: string | null; value: number; unit: string | null; normalized: number }[]
}

export interface Comparison {
  version: string
  matrix: MatrixRow[]
  groups: ComparableGroup[]
  not_comparable: { paper_id: string; evidence_id: string; metric: string; reasons: string[] }[]
  claims: { paper_id: string; evidence_id: string; better: string; worse: string }[]
  conflicts: [string, string][]
}

export interface PaperRef {
  paper_id: string
  title: string
  authors: string[]
  year: number | null
  venue: string | null
  doi: string | null
  url: string | null
  content_kind: string
}

export interface Report {
  schema_version: number
  generator_version: string
  generated_at: string
  question: string
  scope: {
    papers_discovered: number
    full_text: number
    abstract_only: number
    no_text: number
    papers_with_evidence: number
    selection: string
  }
  bottom_line: string
  overall_strength: Strength
  strength_definitions: Record<Strength, string>
  key_findings: Finding[]
  limitations: string[]
  missing_information: string[]
  unresolved_questions: string[]
  comparison: Comparison
  papers: PaperRef[]
  versions: Record<string, string>
}

export interface ReportEnvelope {
  investigation_id: string
  version: number
  created_at: string
  content: Report
}

export interface EvidenceDetail {
  id: string
  investigation_id: string
  field: string
  finding_status: string
  value: Record<string, unknown> | null
  passage: string | null
  passage_kind: 'quotation' | 'paraphrase' | null
  page_number: number | null
  extraction_method: string
  extraction_version: string
  retrieval_method: string | null
  retrieval_score: number | null
  validation_status: string
  checks: { rule: string; outcome: 'pass' | 'fail'; details: string | null; validator_version: string }[]
  created_at: string
  paper_id: string
  paper_title: string
  authors: string[]
  year: number | null
  venue: string | null
  doi: string | null
  paper_url: string | null
  document: {
    content_kind: string
    full_text_unavailable_reason: string | null
    source_url: string | null
    page_count: number | null
    extractor: string
    extractor_version: string
    fetched_at: string | null
  } | null
}
