import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Investigation } from '../api/types'
import { jsonResponse, renderRoute } from '../test/render'

// Test fixture, not real research data.
const FIXTURE: Investigation = {
  id: '6f1c2c1e-3a4b-4c5d-9e8f-0a1b2c3d4e5f',
  question: 'Fixture question about graph neural networks for fraud detection?',
  status: 'queued',
  created_at: '2026-10-22T12:00:00Z',
  updated_at: '2026-10-22T12:00:00Z',
}

const emptyPage = { items: [], total: 0, limit: 10, offset: 0 }

describe('DashboardPage', () => {
  it('shows the empty state when there are no investigations', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(emptyPage))
    renderRoute('/')
    expect(await screen.findByText(/No investigations yet/)).toBeInTheDocument()
  })

  it('lists recent investigations with a text status label', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ ...emptyPage, items: [FIXTURE], total: 1 }),
    )
    renderRoute('/')
    const link = await screen.findByRole('link', { name: new RegExp(FIXTURE.question) })
    expect(link).toHaveAttribute('href', `/investigations/${FIXTURE.id}`)
    expect(screen.getByText('Queued')).toBeInTheDocument()
  })

  it('shows an API error message when the list fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'Database unavailable' }, 503),
    )
    renderRoute('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
  })

  it('blocks too-short questions without calling the API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(emptyPage))
    renderRoute('/')
    await userEvent.type(screen.getByLabelText('Research question'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Start investigation' }))

    expect(screen.getByText('Enter at least 10 characters.')).toBeInTheDocument()
    expect(screen.getByLabelText('Research question')).toHaveAttribute('aria-invalid', 'true')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('submits a valid question and navigates to the investigation', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
      init?.method === 'POST' ? jsonResponse(FIXTURE, 201) : jsonResponse(emptyPage),
    )
    const { router } = renderRoute('/')
    await userEvent.type(screen.getByLabelText('Research question'), `  ${FIXTURE.question}  `)
    await userEvent.click(screen.getByRole('button', { name: 'Start investigation' }))

    await waitFor(() => expect(router.state.location.pathname).toBe(`/investigations/${FIXTURE.id}`))
    const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ question: FIXTURE.question })
  })
})
