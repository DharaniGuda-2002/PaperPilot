import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { jsonResponse, makeInvestigation, mockApi, renderRoute } from '../test/render'

describe('InvestigationsPage', () => {
  it('pages through investigations using the API offset', async () => {
    const api = mockApi({
      'GET /api/v1/investigations': () => {
        const url = new URL(String(api.mock.lastCall?.[0]), 'http://test')
        const offset = Number(url.searchParams.get('offset'))
        const item = makeInvestigation({ id: `id-${offset}`, question: `Fixture question at offset ${offset}?` })
        return jsonResponse({ items: [item], total: 25, limit: 20, offset })
      },
    })
    renderRoute('/app/investigations')

    expect(await screen.findByText('Fixture question at offset 0?')).toBeInTheDocument()
    expect(screen.getByText('1–1 of 25')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Fixture question at offset 20?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })
})
