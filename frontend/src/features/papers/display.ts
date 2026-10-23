import type { FullTextAvailability, Paper } from '../../api/types'
import type { StatusTone } from '../investigations/status'

export const AVAILABILITY_DISPLAY: Record<FullTextAvailability, { label: string; tone: StatusTone }> =
  {
    pdf_available: { label: 'PDF available', tone: 'success' },
    open_access: { label: 'Open access', tone: 'info' },
    not_open_access: { label: 'Not open access', tone: 'neutral' },
  }

export function formatAuthors(authors: string[], max = 3): string {
  if (authors.length === 0) return 'Unknown authors'
  if (authors.length <= max) return authors.join(', ')
  return `${authors.slice(0, max).join(', ')} et al.`
}

export function formatPublication(paper: Paper): string {
  return [paper.publication_year, paper.venue].filter(Boolean).join(' · ')
}
