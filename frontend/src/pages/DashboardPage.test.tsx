import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, makeInvestigation, makeStats, mockApi, renderRoute } from '../test/render'

const emptyPage = { items: [], total: 0, limit: 5, offset: 0 }
const LIST = 'GET /api/v1/investigations'
const STATS = 'GET /api/v1/investigations/stats'

describe('DashboardPage', () => {
  it('shows real summary counts and the empty state', async () => {
    mockApi({
      [LIST]: () => jsonResponse(emptyPage),
      [STATS]: () => jsonResponse(makeStats({ queued: 2, running: 1, completed: 3, partially_completed: 1 })),
    })
    renderRoute('/app')

    const summary = await screen.findByRole('list', { name: 'Investigation summary' })
    const cards = within(summary).getAllByRole('listitem').map((card) => card.textContent)
    expect(cards).toEqual(['7Investigations', '2Queued', '1In progress', '4Completed'])
    expect(await screen.findByText(/No investigations yet/)).toBeInTheDocument()
  })

  it('lists recent investigations linking to their pages with a text status', async () => {
    const fixture = makeInvestigation()
    mockApi({
      [LIST]: () => jsonResponse({ ...emptyPage, items: [fixture], total: 1 }),
      [STATS]: () => jsonResponse(makeStats({ queued: 1 })),
    })
    renderRoute('/app')

    const link = await screen.findByRole('link', { name: new RegExp(fixture.question) })
    expect(link).toHaveAttribute('href', `/app/investigations/${fixture.id}`)
    expect(within(link).getByText('Queued')).toBeInTheDocument()
  })

  it('shows the API error message when loading fails', async () => {
    mockApi({
      [LIST]: () => jsonResponse({ detail: 'Database unavailable' }, 503),
      [STATS]: () => jsonResponse({ detail: 'Database unavailable' }, 503),
    })
    renderRoute('/app')
    const alerts = await screen.findAllByRole('alert')
    expect(alerts[0]).toHaveTextContent('Database unavailable')
  })

  it('fills the input from an example and submits it', async () => {
    const created = makeInvestigation({ id: 'new-id' })
    const api = mockApi({
      [LIST]: () => jsonResponse(emptyPage),
      [STATS]: () => jsonResponse(makeStats()),
      'POST /api/v1/investigations': () => jsonResponse(created, 201),
      'GET /api/v1/investigations/new-id': () => jsonResponse(created),
    })
    const { router } = renderRoute('/app')

    await userEvent.click(await screen.findByRole('button', { name: 'GNNs for fraud detection' }))
    const input = screen.getByLabelText<HTMLInputElement>('What would you like to investigate?')
    expect(input.value).toContain('graph neural networks')
    await userEvent.click(screen.getByRole('button', { name: 'Start investigation' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/app/investigations/new-id'))
    const post = api.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body)).question).toContain('graph neural networks')
  })

  it('blocks too-short questions without calling the API', async () => {
    const api = mockApi({
      [LIST]: () => jsonResponse(emptyPage),
      [STATS]: () => jsonResponse(makeStats()),
    })
    renderRoute('/app')
    await userEvent.type(screen.getByLabelText('What would you like to investigate?'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Start investigation' }))

    expect(screen.getByText('Enter at least 10 characters.')).toBeInTheDocument()
    expect(api.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })
})
