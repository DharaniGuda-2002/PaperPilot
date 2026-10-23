// Centralized HTTP client. All API calls go through `request` so errors are uniform.

import type {
  DiscoveredPaperPage,
  EvidenceItem,
  Investigation,
  InvestigationPage,
  InvestigationStats,
  Paper,
  PaperSearchParams,
  PaperSearchResponse,
  PipelineStatus,
  InvestigationTask,
} from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'Could not reach the PaperPilot API. Check that the backend is running.')
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return (await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    const detail = (body as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    // FastAPI validation errors: [{ msg: "..." }, ...]
    if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  } catch {
    // Non-JSON error body; fall through to a generic message.
  }
  return `Request failed (HTTP ${response.status})`
}

export const api = {
  listInvestigations(limit = 10, offset = 0): Promise<InvestigationPage> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    return request(`/api/v1/investigations?${params}`)
  },

  getInvestigationStats(): Promise<InvestigationStats> {
    return request('/api/v1/investigations/stats')
  },

  getInvestigation(id: string): Promise<Investigation> {
    return request(`/api/v1/investigations/${encodeURIComponent(id)}`)
  },

  getInvestigationTasks(id: string): Promise<InvestigationTask[]> {
    return request(`/api/v1/investigations/${encodeURIComponent(id)}/tasks`)
  },

  getDiscoveredPapers(id: string, limit = 25, offset = 0): Promise<DiscoveredPaperPage> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    return request(`/api/v1/investigations/${encodeURIComponent(id)}/papers?${params}`)
  },

  getEvidence(id: string): Promise<EvidenceItem[]> {
    return request(`/api/v1/investigations/${encodeURIComponent(id)}/evidence`)
  },

  getPipelineStatus(): Promise<PipelineStatus> {
    return request('/api/v1/system/pipeline')
  },

  searchPapers(params: PaperSearchParams): Promise<PaperSearchResponse> {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') query.set(key, String(value))
    }
    return request(`/api/v1/papers/search?${query}`)
  },

  getPaper(id: string): Promise<Paper> {
    return request(`/api/v1/papers/${encodeURIComponent(id)}`)
  },

  createInvestigation(question: string): Promise<Investigation> {
    return request('/api/v1/investigations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
  },
}
