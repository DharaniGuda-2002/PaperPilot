import { ChevronDown, TriangleAlert } from 'lucide-react'

import type { Finding, Strength, StudySupport } from '../../api/report'
import { StrengthBadge } from './StrengthBadge'

const KIND_LABEL = { claim: 'Reported claim', comparison: 'Comparable results', caveat: 'Caveat' }

interface Props {
  finding: Finding
  index: number
  expanded: boolean
  onToggle: () => void
  onCite: (evidenceId: string) => void
  onRelated: (findingId: string) => void
  titles: Record<string, string>
  definitions: Record<Strength, string>
}

/** Level 1 row that expands in place (level 2) without leaving the page. */
export function FindingCard({ finding, index, expanded, onToggle, onCite, onRelated, titles, definitions }: Props) {
  const panelId = `finding-panel-${finding.id}`
  return (
    <li className="finding" id={`finding-${finding.id}`}>
      <h3 className="finding__heading">
        <button type="button" className="finding__toggle" aria-expanded={expanded} aria-controls={panelId} onClick={onToggle}>
          <span className="finding__number" aria-hidden="true">
            {index}
          </span>
          <span className="finding__title">
            {finding.title}
            <span className="finding__meta">
              {KIND_LABEL[finding.kind]}
              {finding.supporting.length > 0 && ` · ${finding.supporting.length} supporting`}
              {finding.conflicting.length > 0 && ` · ${finding.conflicting.length} conflicting`}
            </span>
          </span>
          {finding.strength && <StrengthBadge strength={finding.strength} definition={definitions[finding.strength]} />}
          <ChevronDown className={`finding__chevron${expanded ? ' finding__chevron--open' : ''}`} aria-hidden="true" size={18} />
        </button>
      </h3>
      {/* Caveats near the conclusion they affect stay visible even when collapsed. */}
      {finding.warnings.length > 0 && !expanded && (
        <p className="finding__warning">
          <TriangleAlert aria-hidden="true" size={14} /> {finding.warnings[0]}
        </p>
      )}
      <div id={panelId} className="finding__panel" hidden={!expanded}>
        <p>{finding.summary}</p>
        {finding.strength_reason && (
          <p className="hint">
            Strength: {finding.strength_reason}. {finding.strength && definitions[finding.strength]}
          </p>
        )}
        {finding.warnings.length > 0 && (
          <ul className="warning-list" aria-label="Comparability warnings">
            {finding.warnings.map((w) => (
              <li key={w}>
                <TriangleAlert aria-hidden="true" size={14} /> {w}
              </li>
            ))}
          </ul>
        )}
        {finding.supporting.length > 0 && (
          <Studies label="Supporting studies" studies={finding.supporting} onCite={onCite} />
        )}
        {finding.conflicting.length > 0 && (
          <Studies label="Conflicting evidence" studies={finding.conflicting} onCite={onCite} />
        )}
        {finding.related.length > 0 && (
          <p className="related">
            Related:{' '}
            {finding.related.map((id) => (
              <button key={id} type="button" className="chip" onClick={() => onRelated(id)}>
                {titles[id] ?? id}
              </button>
            ))}
          </p>
        )}
      </div>
    </li>
  )
}

function Studies({ label, studies, onCite }: { label: string; studies: StudySupport[]; onCite: (id: string) => void }) {
  return (
    <section>
      <h4 className="card__subtitle">{label}</h4>
      <ul className="study-list">
        {studies.map((study) => (
          <li key={study.paper_id}>
            <span className="study-list__title">
              {study.title}
              {study.year && ` (${study.year})`}
            </span>
            <span className="hint">
              {study.detail}
              {study.content_kind === 'abstract' && ' · abstract only'}
              {study.content_kind === 'none' && ' · no text available'}
            </span>
            <span className="study-list__cites">
              {study.evidence_ids.map((id, i) => (
                <button key={id} type="button" className="text-link cite" onClick={() => onCite(id)}>
                  Open citation{study.evidence_ids.length > 1 ? ` ${i + 1}` : ''}
                </button>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
