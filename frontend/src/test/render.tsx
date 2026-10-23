import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import type { Investigation, InvestigationStats } from '../api/types'
import { routes } from '../routes'

/** Render the real route tree at `path` with a fresh, retry-free query cache. */
export function renderRoute(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { router }
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Test fixtures below are not real research data.
export function makeInvestigation(overrides: Partial<Investigation> = {}): Investigation {
  return {
    id: '6f1c2c1e-3a4b-4c5d-9e8f-0a1b2c3d4e5f',
    question: 'Fixture question about graph neural networks for fraud detection?',
    status: 'queued',
    created_at: '2026-10-22T12:00:00Z',
    updated_at: '2026-10-22T12:00:00Z',
    ...overrides,
  }
}

export function makeStats(overrides: Partial<InvestigationStats['by_status']> = {}): InvestigationStats {
  const by_status = {
    queued: 0,
    running: 0,
    completed: 0,
    partially_completed: 0,
    failed: 0,
    cancelled: 0,
    ...overrides,
  }
  return { total: Object.values(by_status).reduce((a, b) => a + b, 0), by_status }
}

/** Route fetch calls by URL path. Unmatched paths fail the test loudly. */
export function mockApi(handlers: Record<string, (init?: RequestInit) => Response>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://test').pathname
    const method = init?.method ?? 'GET'
    const handler = handlers[`${method} ${path}`]
    if (!handler) throw new Error(`Unexpected request: ${method} ${path}`)
    return handler(init)
  })
}
