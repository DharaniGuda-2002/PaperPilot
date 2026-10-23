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
    expect(screen.getAllByText(/Not built yet ·/)).toHaveLength(5)
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
