import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { jsonResponse, renderRoute } from '../test/render'

describe('InvestigationPage', () => {
  it('shows the question, status, and the honest pipeline notice', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        id: 'abc',
        question: 'Fixture question for the detail page test?',
        status: 'queued',
        created_at: '2026-10-22T12:00:00Z',
        updated_at: '2026-10-22T12:00:00Z',
      }),
    )
    renderRoute('/investigations/abc')
    expect(
      await screen.findByRole('heading', { name: 'Fixture question for the detail page test?' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Queued')).toBeInTheDocument()
    expect(screen.getByText(/processing pipeline is not built yet/)).toBeInTheDocument()
  })

  it('shows a not-found state for unknown investigations', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'Investigation not found' }, 404),
    )
    renderRoute('/investigations/missing')
    expect(
      await screen.findByRole('heading', { name: 'Investigation not found' }),
    ).toBeInTheDocument()
  })

  it('reports an unreachable API', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    renderRoute('/investigations/abc')
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the PaperPilot API')
  })
})
