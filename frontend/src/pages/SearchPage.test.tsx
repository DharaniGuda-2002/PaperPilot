import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { makePaper, makeSearchResponse } from '../test/papers'
import { jsonResponse, mockApi, renderRoute } from '../test/render'

const SEARCH = 'GET /api/v1/papers/search'

function lastSearchParams(api: ReturnType<typeof mockApi>) {
  const urls = api.mock.calls
    .map(([input]) => new URL(String(input), 'http://test'))
    .filter((url) => url.pathname === '/api/v1/papers/search')
  return urls.at(-1)!.searchParams
}

describe('SearchPage', () => {
  it('starts with suggestions and does not call the API without a query', () => {
    const api = mockApi({})
    renderRoute('/app/search')
    expect(screen.getByRole('heading', { name: 'Find relevant papers' })).toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
  })

  it('searches, shows results with availability and author summary', async () => {
    const api = mockApi({ [SEARCH]: () => jsonResponse(makeSearchResponse([makePaper()], { total: 4321 })) })
    const { router } = renderRoute('/app/search')

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search papers' }), 'graph learning')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByRole('heading', { name: '4,321 papers' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('?q=graph+learning')
    expect(lastSearchParams(api).get('q')).toBe('graph learning')
    expect(screen.getByRole('link', { name: 'Fixture paper on graph learning' })).toHaveAttribute(
      'href',
      '/app/papers/paper-1',
    )
    expect(screen.getByText(/Ada Example, Ben Sample, Cy Placeholder et al\./)).toBeInTheDocument()
    expect(screen.getByText('PDF available')).toBeInTheDocument()
    expect(screen.getByText('1,234 citations')).toBeInTheDocument()
  })

  it('sends filters from the URL to the API and resets paging when they change', async () => {
    const api = mockApi({
      [SEARCH]: () => jsonResponse(makeSearchResponse([makePaper()], { total: 100, page: 2 })),
    })
    renderRoute('/app/search?q=graph+learning&page=2')
    await screen.findByText('Page 2 of 10')

    await userEvent.click(screen.getByRole('checkbox', { name: 'Open access only' }))
    await waitFor(() => expect(lastSearchParams(api).get('open_access_only')).toBe('true'))
    expect(lastSearchParams(api).get('page')).toBe('1')

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sort by' }), 'citations')
    await waitFor(() => expect(lastSearchParams(api).get('sort')).toBe('citations'))
  })

  it('does not render links with unsafe URL schemes', async () => {
    mockApi({
      [SEARCH]: () =>
        jsonResponse(
          makeSearchResponse([makePaper({ pdf_url: 'javascript:alert(1)', landing_page_url: null })]),
        ),
    })
    renderRoute('/app/search?q=graph+learning')
    await screen.findByRole('link', { name: 'Fixture paper on graph learning' })
    expect(screen.queryByRole('link', { name: /PDF/ })).not.toBeInTheDocument()
  })

  it('shows the provider-unavailable message', async () => {
    mockApi({
      [SEARCH]: () =>
        jsonResponse({ detail: 'The paper search provider is unavailable right now.' }, 503),
    })
    renderRoute('/app/search?q=graph+learning')
    expect(await screen.findByRole('alert')).toHaveTextContent('provider is unavailable')
  })

  it('rejects too-short queries locally', async () => {
    const api = mockApi({})
    renderRoute('/app/search')
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search papers' }), 'ab')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(screen.getByText('Enter at least 3 characters.')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
  })
})
