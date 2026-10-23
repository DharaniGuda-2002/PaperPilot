// Mirrors backend/app/investigations/schemas.py. Keep in sync with the API.

export type InvestigationStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'partially_completed'
  | 'failed'
  | 'cancelled'

export interface Investigation {
  id: string
  question: string
  status: InvestigationStatus
  created_at: string
  updated_at: string
}

export interface InvestigationPage {
  items: Investigation[]
  total: number
  limit: number
  offset: number
}

export interface InvestigationStats {
  total: number
  by_status: Record<InvestigationStatus, number>
}

// Mirrors backend/app/papers/schemas.py.
export type FullTextAvailability = 'pdf_available' | 'open_access' | 'not_open_access'
export type SearchSort = 'relevance' | 'citations' | 'newest'

export interface Paper {
  id: string
  provider: string
  provider_id: string
  doi: string | null
  title: string
  authors: string[]
  publication_year: number | null
  venue: string | null
  work_type: string | null
  abstract: string | null
  cited_by_count: number | null
  is_open_access: boolean
  oa_status: string | null
  pdf_url: string | null
  landing_page_url: string | null
  license: string | null
  metadata_fetched_at: string
  full_text_availability: FullTextAvailability
}

export interface PaperSearchParams {
  q: string
  from_year?: number
  to_year?: number
  open_access_only?: boolean
  sort?: SearchSort
  page?: number
  per_page?: number
}

export interface PaperSearchResponse {
  query: string
  provider: string
  total: number
  page: number
  per_page: number
  cached: boolean
  fetched_at: string
  results: { paper: Paper; relevance_score: number | null }[]
}

export const SEARCH_QUERY_MIN_LENGTH = 3
export const SEARCH_MAX_PAGE = 50

export const QUESTION_MIN_LENGTH = 10
export const QUESTION_MAX_LENGTH = 500
