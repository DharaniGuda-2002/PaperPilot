import type { Strength } from '../../api/report'

const LEVELS: Strength[] = ['insufficient', 'limited', 'moderate', 'strong']
const LABELS: Record<Strength, string> = {
  insufficient: 'Insufficient',
  limited: 'Limited',
  moderate: 'Moderate',
  strong: 'Strong',
}

/** Four-step scale showing where the report sits. Counts checkable sources; not a model confidence. */
export function StrengthMeter({ strength, definition }: { strength: Strength; definition?: string }) {
  const position = LEVELS.indexOf(strength)
  return (
    <div className="meter">
      <ol className="meter__scale" aria-label={`Evidence strength: ${LABELS[strength]} (step ${position + 1} of 4)`}>
        {LEVELS.map((level, index) => (
          <li
            key={level}
            className={`meter__step${index <= position ? ' meter__step--filled' : ''}${index === position ? ' meter__step--current' : ''}`}
            aria-current={index === position ? 'step' : undefined}
          >
            <span className="meter__bar" aria-hidden="true" />
            <span className="meter__label">{LABELS[level]}</span>
          </li>
        ))}
      </ol>
      {definition && <p className="meter__definition">{definition}</p>}
    </div>
  )
}
