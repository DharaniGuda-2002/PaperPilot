import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { EvidenceDetail, Report } from '../api/report'
import { jsonResponse, mockApi, renderRoute } from '../test/render'

// Test fixtures, not real research data.
const REPORT: Report = {
  schema_version: 1,
  generator_version: 'report-v1',
  generated_at: '2026-10-23T12:00:00Z',
  question: 'Fixture question about GNNs versus gradient boosting?',
  scope: { papers_discovered: 4, full_text: 3, abstract_only: 1, no_text: 0, papers_with_evidence: 4, selection: 'Top 4 OpenAlex results.' },
  bottom_line: 'Fixture bottom line. This summarizes reported evidence; it does not establish which method is better.',
  overall_strength: 'moderate',
  strength_definitions: {
    strong: 'Strong definition.',
    moderate: 'Moderate definition.',
    limited: 'Limited definition.',
    insufficient: 'Insufficient definition.',
  },
  key_findings: [
    {
      id: 'claim-1',
      kind: 'claim',
      title: 'Graph neural networks reported to outperform Gradient-boosted trees',
      summary: '2 papers report it.',
      strength: 'moderate',
      strength_reason: '2 papers',
      supporting: [{ paper_id: 'p1', title: 'Fixture paper one', year: 2024, content_kind: 'full_text', detail: 'Authors report…', evidence_ids: ['e1'] }],
      conflicting: [],
      warnings: ['Papers use different datasets (A, B).'],
      related: ['caveat-comparability'],
    },
    {
      id: 'caveat-comparability',
      kind: 'caveat',
      title: 'Most reported results cannot be compared directly',
      summary: '5 of 6 results lack a dataset.',
      strength: null,
      strength_reason: null,
      supporting: [],
      conflicting: [],
      warnings: [],
      related: ['claim-1'],
    },
  ],
  limitations: ['Facts were extracted by rules.'],
  missing_information: ['Evaluation split or protocol not found in 2 of 3 full-text papers.'],
  unresolved_questions: ['No two papers report the same metric on the same dataset and protocol.'],
  comparison: {
    version: 'compare-v1',
    matrix: [
      {
        paper_id: 'p1', title: 'Fixture paper one', year: 2024, content_kind: 'full_text', methods: ['GNN'],
        proposed_methods: ['GNN'], datasets: ['YelpChi'], protocols: [], baselines: ['XGBoost'],
        results: [{ evidence_id: 'e2', metric: 'AUC', value: 0.92, unit: 'ratio', normalized: 0.92, method: 'GNN', page: 3 }],
        missing_fields: ['split'], warnings: ['Evaluation split or protocol not found.'],
      },
    ],
    groups: [],
    not_comparable: [{ paper_id: 'p1', evidence_id: 'e2', metric: 'AUC', reasons: ['evaluation protocol not reported'] }],
    claims: [],
    conflicts: [],
  },
  papers: [{ paper_id: 'p1', title: 'Fixture paper one', authors: ['A. Author'], year: 2024, venue: 'Fixture Venue', doi: '10.1000/x', url: null, content_kind: 'full_text' }],
  versions: { extraction: 'rules-v2', validation: 'checks-v1', comparison: 'compare-v1' },
}  // fmt: skip

const DETAIL: EvidenceDetail = {
  id: 'e1', investigation_id: 'abc', field: 'baseline', finding_status: 'reported', value: { name: 'XGBoost' },
  passage: 'Our GNN outperforms XGBoost on the fixture dataset.', passage_kind: 'quotation', page_number: 4,
  extraction_method: 'rules', extraction_version: 'rules-v2', retrieval_method: 'fts+vector', retrieval_score: 0.0312,
  validation_status: 'verified',
  checks: [{ rule: 'passage_in_source', outcome: 'pass', details: 'exact quotation found in stored text', validator_version: 'checks-v1' }],
  created_at: '2026-10-23T12:00:00Z', paper_id: 'p1', paper_title: 'Fixture paper one', authors: ['A. Author'],
  year: 2024, venue: 'Fixture Venue', doi: '10.1000/x', paper_url: null,
  document: { content_kind: 'full_text', full_text_unavailable_reason: null, source_url: 'https://example.org/p.pdf', page_count: 9, extractor: 'pymupdf', extractor_version: 'x', fetched_at: null },
}  // fmt: skip

function mockReport() {
  return mockApi({
    'GET /api/v1/investigations/abc/report': () =>
      jsonResponse({ investigation_id: 'abc', version: 1, created_at: '2026-10-23T12:00:00Z', content: REPORT }),
    'GET /api/v1/evidence/e1': () => jsonResponse(DETAIL),
  })
}

describe('ReportPage', () => {
  it('shows the quick-scan summary with scope, strength, and limits', async () => {
    mockReport()
    renderRoute('/app/investigations/abc/report')
    expect(await screen.findByText(/Fixture bottom line/)).toBeInTheDocument()
    const scope = screen.getByRole('list', { name: 'Report scope' })
    expect(within(scope).getAllByRole('listitem').map((i) => i.textContent)).toEqual([
      '4Papers discovered',
      '3Full texts analyzed',
      '1Abstracts only',
      '4Papers with evidence',
    ])
    expect(screen.getAllByText('Moderate evidence').length).toBeGreaterThan(0)
    expect(screen.getByText('Facts were extracted by rules.')).toBeInTheDocument()
    expect(screen.getByText(/No two papers report the same metric/)).toBeInTheDocument()
  })

  it('expands a finding in place and keeps its caveat visible while collapsed', async () => {
    mockReport()
    renderRoute('/app/investigations/abc/report')
    const toggle = await screen.findByRole('button', { name: /Graph neural networks reported to outperform/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('2 papers report it.')).not.toBeVisible()
    const visibleWarnings = () =>
      screen.getAllByText(/Papers use different datasets/).filter((el) => el.closest('[hidden]') === null)
    expect(visibleWarnings()).toHaveLength(1) // caveat stays next to the collapsed finding

    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('2 papers report it.')).toBeVisible()
    expect(screen.getByText('Fixture paper one (2024)')).toBeInTheDocument()

    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens the evidence inspector from a citation', async () => {
    mockReport()
    renderRoute('/app/investigations/abc/report')
    await userEvent.click(await screen.findByRole('button', { name: /Graph neural networks reported to outperform/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Open citation' }))

    const dialog = await screen.findByRole('dialog', { name: 'Evidence inspector', hidden: true })
    expect(await within(dialog).findByText('Exact quotation from the paper · page 4')).toBeInTheDocument()
    expect(within(dialog).getByText('“Our GNN outperforms XGBoost on the fixture dataset.”')).toBeInTheDocument()
    expect(within(dialog).getByText('Quotation found in the stored text')).toBeInTheDocument()
    expect(within(dialog).getByText('Full text (open-access PDF)')).toBeInTheDocument()
  })

  it('switches to the comparison matrix with arrow keys', async () => {
    mockReport()
    const { router } = renderRoute('/app/investigations/abc/report')
    const summaryTab = await screen.findByRole('tab', { name: 'Summary' })
    summaryTab.focus()
    await userEvent.keyboard('{ArrowRight}')
    await waitFor(() => expect(router.state.location.search).toBe('?view=comparison'))
    expect(screen.getByRole('tab', { name: 'Comparison' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/No two papers report the same metric on the same dataset under/)).toBeInTheDocument()
    const matrix = screen.getByRole('table')
    expect(within(matrix).getByText('GNN (proposed)')).toBeInTheDocument()
    expect(within(matrix).getByText('Evaluation split or protocol not found.')).toBeInTheDocument()
  })

  it('explains when the report is not ready', async () => {
    mockApi({ 'GET /api/v1/investigations/abc/report': () => jsonResponse({ detail: 'Report not ready' }, 404) })
    renderRoute('/app/investigations/abc/report')
    expect(await screen.findByRole('heading', { name: 'Report not ready' })).toBeInTheDocument()
  })
})
