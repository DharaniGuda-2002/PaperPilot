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

export const QUESTION_MIN_LENGTH = 10
export const QUESTION_MAX_LENGTH = 500
