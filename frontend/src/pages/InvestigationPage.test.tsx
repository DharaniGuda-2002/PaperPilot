import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { jsonResponse, makeInvestigation, mockApi, renderRoute } from '../test/render'

describe('InvestigationPage', () => {
  it('shows the question, real status, and unbuilt stages honestly', async () => {
    const fixture = makeInvestigation({ id: 'abc' })
    mockApi({ 'GET /api/v1/investigations/abc': () => jsonResponse(fixture) })
    renderRoute('/app/investigations/abc')

    expect(await screen.findByRole('heading', { name: fixture.question })).toBeInTheDocument()
    expect(screen.getAllByText('Queued').length).toBeGreaterThan(0)
    expect(screen.getByText(/processing pipeline is not built yet/)).toBeInTheDocument()
    expect(screen.getAllByText(/Not built yet ·/)).toHaveLength(6)
  })

  it('shows a not-found state for unknown investigations', async () => {
    mockApi({
      'GET /api/v1/investigations/missing': () =>
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
    mockApi({ 'GET /api/v1/investigations/abc': () => jsonResponse(makeInvestigation({ id: 'abc' })) })
    const { router } = renderRoute('/investigations/abc')
    await waitFor(() => expect(router.state.location.pathname).toBe('/app/investigations/abc'))
  })
})
