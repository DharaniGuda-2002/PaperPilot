import type { FullTextAvailability } from '../../api/types'
import { AVAILABILITY_DISPLAY } from './display'

export function AvailabilityBadge({ value }: { value: FullTextAvailability }) {
  const { label, tone } = AVAILABILITY_DISPLAY[value]
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>
}
