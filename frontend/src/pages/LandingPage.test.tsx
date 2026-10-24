import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderRoute } from '../test/render'

describe('LandingPage', () => {
  it('presents the product, an app entry point, and an honest preview notice', () => {
    renderRoute('/')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Ask a research question. Get answers you can check.',
    )
    expect(screen.getByRole('link', { name: 'Open app' })).toHaveAttribute('href', '/app')
    expect(screen.getByText(/About this public demo/)).toBeInTheDocument()
    const nav = within(screen.getByRole('navigation', { name: 'Site' }))
    expect(nav.getByRole('link', { name: 'FAQ' })).toHaveAttribute('href', '/faq')
    expect(nav.getByRole('link', { name: 'About' })).toHaveAttribute('href', '/about')
    expect(screen.getByLabelText('Research question')).toBeInTheDocument()
  })
})
