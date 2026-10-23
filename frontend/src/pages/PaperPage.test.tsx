import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { makePaper } from '../test/papers'
import { jsonResponse, mockApi, renderRoute } from '../test/render'

describe('PaperPage', () => {
  it('shows metadata, provenance, and safe outbound links', async () => {
    mockApi({ 'GET /api/v1/papers/paper-1': () => jsonResponse(makePaper()) })
    renderRoute('/app/papers/paper-1')

    expect(
      await screen.findByRole('heading', { name: 'Fixture paper on graph learning' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Fixture abstract text.')).toBeInTheDocument()
    expect(screen.getByText(/has not analyzed this paper yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '10.1000/fixture' })).toHaveAttribute(
      'href',
      'https://doi.org/10.1000/fixture',
    )
    expect(screen.getByRole('link', { name: /Open PDF/ })).toHaveAttribute(
      'href',
      'https://example.org/paper.pdf',
    )
    expect(screen.getByText('W123')).toBeInTheDocument()
  })

  it('says when no abstract is available instead of inventing one', async () => {
    mockApi({
      'GET /api/v1/papers/paper-1': () =>
        jsonResponse(makePaper({ abstract: null, pdf_url: null, full_text_availability: 'not_open_access' })),
    })
    renderRoute('/app/papers/paper-1')
    expect(await screen.findByText(/does not provide an abstract/)).toBeInTheDocument()
    expect(screen.getByText('Not open access')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open PDF/ })).not.toBeInTheDocument()
  })

  it('shows not found for unknown papers', async () => {
    mockApi({
      'GET /api/v1/papers/missing': () => jsonResponse({ detail: 'Paper not found' }, 404),
    })
    renderRoute('/app/papers/missing')
    expect(await screen.findByRole('heading', { name: 'Paper not found' })).toBeInTheDocument()
  })
})
