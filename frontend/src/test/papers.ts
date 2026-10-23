import type { Paper, PaperSearchResponse } from '../api/types'

// Test fixtures, not real research data.
export function makePaper(overrides: Partial<Paper> = {}): Paper {
  return {
    id: 'paper-1',
    provider: 'openalex',
    provider_id: 'W123',
    doi: '10.1000/fixture',
    title: 'Fixture paper on graph learning',
    authors: ['Ada Example', 'Ben Sample', 'Cy Placeholder', 'Dee Fourth'],
    publication_year: 2022,
    venue: 'Fixture Conference',
    work_type: 'article',
    abstract: 'Fixture abstract text.',
    cited_by_count: 1234,
    is_open_access: true,
    oa_status: 'green',
    pdf_url: 'https://example.org/paper.pdf',
    landing_page_url: 'https://example.org/paper',
    license: 'cc-by',
    metadata_fetched_at: '2026-10-22T12:00:00Z',
    full_text_availability: 'pdf_available',
    ...overrides,
  }
}

export function makeSearchResponse(papers: Paper[], overrides: Partial<PaperSearchResponse> = {}) {
  return {
    query: 'graph learning',
    provider: 'openalex',
    total: papers.length,
    page: 1,
    per_page: 10,
    cached: false,
    fetched_at: new Date().toISOString(),
    results: papers.map((paper) => ({ paper, relevance_score: 1 })),
    ...overrides,
  } satisfies PaperSearchResponse
}
