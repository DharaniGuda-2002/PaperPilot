import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderRoute } from '../test/render'

describe('LandingPage', () => {
  it('presents the product, an app entry point, and an honest preview notice', () => {
    renderRoute('/')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Turn research papers into clear insights.',
    )
    expect(screen.getByRole('link', { name: 'Open app' })).toHaveAttribute('href', '/app')
    expect(screen.getByText(/Early preview/)).toBeInTheDocument()
    expect(screen.getByLabelText('Research question')).toBeInTheDocument()
  })
})
