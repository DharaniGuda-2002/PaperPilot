import type { InvestigationStatus } from '../../api/types'

export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'error'

export const STATUS_DISPLAY: Record<InvestigationStatus, { label: string; tone: StatusTone }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  running: { label: 'Running', tone: 'info' },
  completed: { label: 'Completed', tone: 'success' },
  partially_completed: { label: 'Partially completed', tone: 'warning' },
  failed: { label: 'Failed', tone: 'error' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}
