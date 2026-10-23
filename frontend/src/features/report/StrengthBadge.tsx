import type { Strength } from '../../api/report'
import type { StatusTone } from '../investigations/status'

const DISPLAY: Record<Strength, { label: string; tone: StatusTone }> = {
  strong: { label: 'Strong evidence', tone: 'success' },
  moderate: { label: 'Moderate evidence', tone: 'info' },
  limited: { label: 'Limited evidence', tone: 'warning' },
  insufficient: { label: 'Insufficient evidence', tone: 'neutral' },
}

/** Strength of supporting evidence, with its published definition as a tooltip.
 *  Not a model confidence. */
export function StrengthBadge({ strength, definition }: { strength: Strength; definition?: string }) {
  const { label, tone } = DISPLAY[strength]
  return (
    <span className={`status-badge status-badge--${tone}`} title={definition}>
      {label}
    </span>
  )
}
