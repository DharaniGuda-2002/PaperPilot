import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderRoute } from '../test/render'

describe('LandingPage', () => {
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
