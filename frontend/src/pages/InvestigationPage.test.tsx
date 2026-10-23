import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { InvestigationTask } from '../api/types'
import { makePaper } from '../test/papers'
import { jsonResponse, makeInvestigation, mockApi, renderRoute } from '../test/render'

const BASE = 'GET /api/v1/investigations/abc'

// Test fixtures, not real research data.
function makeTask(overrides: Partial<InvestigationTask> = {}): InvestigationTask {
  return {
    id: 'task-1',
    kind: 'discover_papers',
    subject_key: '',
    status: 'pending',
    attempts: 0,
    last_error: null,
    result_summary: null,
    started_at: null,
    finished_at: null,
    created_at: '2026-10-22T12:00:00Z',
    ...overrides,
  }
}

function discoveryStage() {
  return screen.getByText('Discovering relevant papers').closest('li')!
}

describe('InvestigationPage', () => {
  it('shows completed discovery with the papers it linked', async () => {
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc', status: 'running' })),
      [`${BASE}/tasks`]: () =>
        jsonResponse([
          makeTask({
            status: 'succeeded',
            attempts: 1,
            result_summary: { papers_linked: 1, papers_available: 1309 },
          }),
        ]),
      [`${BASE}/papers`]: () =>
        jsonResponse({
          items: [
            {
              rank: 1,
              relevance_score: 12.5,
              retrieval_method: 'openalex_search',
              discovered_at: '2026-10-22T12:00:02Z',
              paper: makePaper(),
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        }),
    })
    renderRoute('/app/investigations/abc')

    await screen.findByText('Discovering relevant papers')
    await waitFor(() => expect(within(discoveryStage()).getByText('Completed')).toBeInTheDocument())
    expect(within(discoveryStage()).getByText('1 papers found')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Fixture paper on graph learning' })).toBeInTheDocument()
    expect(screen.getByText(/Top 1 by relevance of 1,309 matches/)).toBeInTheDocument()
    expect(screen.queryByText(/Not built yet/)).not.toBeInTheDocument()
    const reportStage = screen.getByText('Comparing results and writing the report').closest('li')!
    expect(within(reportStage).getByText('Waiting')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /View report/ })).not.toBeInTheDocument()
  })

  it('aggregates per-paper stages and shows evidence with quotations', async () => {
    const paperTask = (kind: string, status: InvestigationTask['status'], summary: Record<string, unknown> | null) =>
      makeTask({ id: `${kind}-${Math.random()}`, kind, subject_key: 'p1', status, result_summary: summary })
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc', status: 'running' })),
      [`${BASE}/tasks`]: () =>
        jsonResponse([
          makeTask({ status: 'succeeded', result_summary: { papers_linked: 2 } }),
          paperTask('process_document', 'succeeded', { content_kind: 'full_text' }),
          paperTask('process_document', 'succeeded', { content_kind: 'abstract' }),
          paperTask('extract_evidence', 'succeeded', { records: 3, verified: 2, rejected: 1 }),
          paperTask('extract_evidence', 'running', null),
        ]),
      [`${BASE}/papers`]: () => jsonResponse({ items: [], total: 0, limit: 25, offset: 0 }),
      [`${BASE}/evidence`]: () =>
        jsonResponse([
          {
            id: 'e1',
            paper_id: 'p1',
            paper_title: 'Fixture paper on graph learning',
            field: 'metric_result',
            finding_status: 'reported',
            value: { metric: 'AUC', value: 0.92, unit: 'ratio', method_hint: 'GNN' },
            passage: 'The GNN reaches an AUC of 0.92.',
            passage_kind: 'quotation',
            page_number: 3,
            extraction_method: 'rules',
            extraction_version: 'rules-v1',
            retrieval_method: 'fts+vector',
            retrieval_score: 0.03,
            validation_status: 'verified',
            checks: [],
            created_at: '2026-10-22T12:00:00Z',
          },
          {
            id: 'e2',
            paper_id: 'p1',
            paper_title: 'Fixture paper on graph learning',
            field: 'code_availability',
            finding_status: 'not_found',
            value: null,
            passage: null,
            passage_kind: null,
            page_number: null,
            extraction_method: 'rules',
            extraction_version: 'rules-v1',
            retrieval_method: null,
            retrieval_score: null,
            validation_status: 'unvalidated',
            checks: [],
            created_at: '2026-10-22T12:00:00Z',
          },
        ]),
    })
    renderRoute('/app/investigations/abc')

    const documents = (await screen.findByText('Downloading and processing papers')).closest('li')!
    expect(within(documents).getByText('2 of 2 papers done')).toBeInTheDocument()
    expect(within(documents).getByText('1 full text, 1 abstract only')).toBeInTheDocument()
    expect(within(documents).getByText('Completed')).toBeInTheDocument()
    const extraction = screen.getByText('Extracting evidence').closest('li')!
    expect(within(extraction).getByText('In progress')).toBeInTheDocument()
    expect(within(extraction).getByText('3 facts extracted')).toBeInTheDocument()
    const validation = screen.getByText('Validating findings').closest('li')!
    expect(within(validation).getByText('2 verified, 1 rejected')).toBeInTheDocument()

    expect(await screen.findByText('AUC 0.92 · GNN')).toBeInTheDocument()
    expect(screen.getByText('“The GNN reaches an AUC of 0.92.”', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/Page 3 · quotation · found by fts\+vector/)).toBeInTheDocument()
    expect(screen.getByText(/Not found in the full text: Code\./)).toBeInTheDocument()
  })

  it('links to the report once it is built', async () => {
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc', status: 'completed' })),
      [`${BASE}/tasks`]: () =>
        jsonResponse([
          makeTask({ status: 'succeeded', result_summary: { papers_linked: 0 } }),
          makeTask({ id: 'r', kind: 'build_report', status: 'succeeded', result_summary: { version: 1, findings: 4 } }),
        ]),
      [`${BASE}/papers`]: () => jsonResponse({ items: [], total: 0, limit: 25, offset: 0 }),
    })
    renderRoute('/app/investigations/abc')
    const link = await screen.findByRole('link', { name: /View report/ })
    expect(link).toHaveAttribute('href', '/app/investigations/abc/report')
    const reportStage = screen.getByText('Comparing results and writing the report').closest('li')!
    expect(within(reportStage).getByText('Version 1 · 4 key findings')).toBeInTheDocument()
  })

  it('warns when the event is waiting and no worker is processing', async () => {
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc' })),
      [`${BASE}/tasks`]: () => jsonResponse([makeTask()]),
      'GET /api/v1/system/pipeline': () =>
        jsonResponse({ outbox_backlog: 3, oldest_pending_seconds: 600 }),
    })
    renderRoute('/app/investigations/abc')
    expect(await screen.findByText(/Waiting for a background worker/)).toBeInTheDocument()
    expect(within(discoveryStage()).getByText('Waiting')).toBeInTheDocument()
  })

  it('shows the recorded failure reason', async () => {
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc', status: 'failed' })),
      [`${BASE}/tasks`]: () =>
        jsonResponse([
          makeTask({ status: 'failed_permanent', last_error: 'No papers found for this question' }),
        ]),
    })
    renderRoute('/app/investigations/abc')
    await screen.findByText('Discovering relevant papers')
    await waitFor(() =>
      expect(within(discoveryStage()).getByText('No papers found for this question')).toBeInTheDocument(),
    )
    expect(within(discoveryStage()).getByText('Failed')).toBeInTheDocument()
  })

  it('explains investigations created before the pipeline existed', async () => {
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc' })),
      [`${BASE}/tasks`]: () => jsonResponse([]),
    })
    renderRoute('/app/investigations/abc')
    expect(await screen.findByText(/created before the pipeline/)).toBeInTheDocument()
  })

  it('shows a not-found state for unknown investigations', async () => {
    mockApi({
      'GET /api/v1/investigations/missing': () =>
        jsonResponse({ detail: 'Investigation not found' }, 404),
      'GET /api/v1/investigations/missing/tasks': () =>
        jsonResponse({ detail: 'Investigation not found' }, 404),
    })
    renderRoute('/app/investigations/missing')
    expect(await screen.findByRole('heading', { name: 'Investigation not found' })).toBeInTheDocument()
  })

  it('reports an unreachable API', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    renderRoute('/app/investigations/abc')
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the PaperPilot API')
  })

  it('redirects links from before the /app move', async () => {
    mockApi({
      [BASE]: () => jsonResponse(makeInvestigation({ id: 'abc' })),
      [`${BASE}/tasks`]: () => jsonResponse([]),
    })
    const { router } = renderRoute('/investigations/abc')
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/investigations/abc'))
  })
})
