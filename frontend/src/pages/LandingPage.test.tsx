import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, makeInvestigation, mockApi, renderRoute } from '../test/render'

describe('LandingPage', () => {
  it('links to a finished example when the server has one', async () => {
    const example = makeInvestigation({ is_example: true, status: 'completed' })
    mockApi({ 'GET /api/v1/investigations/examples': () => jsonResponse([example]) })
    renderRoute('/')
    const link = await screen.findByRole('link', { name: 'See a finished example' })
    expect(link).toHaveAttribute('href', `/app/investigations/${example.id}/report`)
  })

  it('falls back to the FAQ link when there is no example', async () => {
    mockApi({ 'GET /api/v1/investigations/examples': () => jsonResponse([]) })
    renderRoute('/')
    await waitFor(() => expect(screen.getByRole('link', { name: 'Read the FAQ' })).toBeInTheDocument())
    expect(screen.queryByRole('link', { name: 'See a finished example' })).not.toBeInTheDocument()
  })

  it('presents the product, clear calls to action, and an honest demo notice', () => {
    renderRoute('/')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Ask a research question. Get answers you can check.',
    )
    expect(screen.queryByRole('link', { name: 'Open app' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/app/investigations/new')
    expect(screen.getByRole('link', { name: 'Start an investigation' })).toHaveAttribute(
      'href',
      '/app/investigations/new',
    )
    expect(screen.getByText(/questions are saved but not analyzed here/)).toBeInTheDocument()
    const nav = within(screen.getByRole('navigation', { name: 'Site' }))
    expect(nav.getByRole('link', { name: 'FAQ' })).toHaveAttribute('href', '/faq')
    expect(nav.getByRole('link', { name: 'About' })).toHaveAttribute('href', '/about')
    expect(screen.queryByLabelText('Research question')).not.toBeInTheDocument()
  })
})
