import type { InvestigationStatus } from '../api/types'
import { STATUS_DISPLAY } from '../features/investigations/status'

export function StatusBadge({ status }: { status: InvestigationStatus }) {
  const { label, tone } = STATUS_DISPLAY[status]
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>
}
