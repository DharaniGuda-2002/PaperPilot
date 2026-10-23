import type { EvidenceItem } from '../../api/types'
import { describeValue, FIELD_LABELS, FIELD_ORDER } from './format'

interface PaperGroup {
  paperId: string
  title: string
  reported: EvidenceItem[]
  absent: EvidenceItem[]
}

function group(items: EvidenceItem[]): PaperGroup[] {
  const groups = new Map<string, PaperGroup>()
  for (const item of items) {
    const entry = groups.get(item.paper_id) ?? {
      paperId: item.paper_id,
      title: item.paper_title,
      reported: [],
      absent: [],
    }
    ;(item.finding_status === 'reported' ? entry.reported : entry.absent).push(item)
    groups.set(item.paper_id, entry)
  }
  const order = (i: EvidenceItem) => FIELD_ORDER.indexOf(i.field)
  for (const entry of groups.values()) entry.reported.sort((a, b) => order(a) - order(b))
  return [...groups.values()].sort((a, b) => b.reported.length - a.reported.length)
}

export function EvidencePreview({ items }: { items: EvidenceItem[] }) {
  const papers = group(items)
  return (
    <div className="evidence-papers">
      {papers.map((paper) => {
        const verified = paper.reported.filter((i) => i.validation_status === 'verified').length
        const abstractOnly = paper.absent.some((i) => i.finding_status === 'unavailable')
        return (
          <details key={paper.paperId} className="evidence-paper">
            <summary>
              <span className="evidence-paper__title">{paper.title}</span>
              <span className="evidence-paper__meta">
                {paper.reported.length} facts · {verified} verified
                {abstractOnly && ' · abstract only'}
              </span>
            </summary>
            {paper.reported.length > 0 && (
              <ul className="evidence-list">
                {paper.reported.map((item) => (
                  <EvidenceRow key={item.id} item={item} />
                ))}
              </ul>
            )}
            {paper.absent.length > 0 && (
              <p className="hint">
                {abstractOnly ? 'Not available (abstract only): ' : 'Not found in the full text: '}
                {paper.absent.map((i) => FIELD_LABELS[i.field]).join(', ')}. Missing text is not
                evidence that something is absent from the study.
              </p>
            )}
          </details>
        )
      })}
    </div>
  )
}

function EvidenceRow({ item }: { item: EvidenceItem }) {
  const failed = item.checks.filter((c) => c.outcome === 'fail')
  const verified = item.validation_status === 'verified'
  return (
    <li className="evidence-item">
      <div className="evidence-item__head">
        <span className="evidence-item__field">{FIELD_LABELS[item.field]}</span>
        <span className="evidence-item__value">{describeValue(item)}</span>
        <span
          className={`status-badge status-badge--${verified ? 'success' : 'error'}`}
          title={failed.map((c) => `${c.rule}: ${c.details}`).join('; ') || undefined}
        >
          {verified ? 'Verified' : 'Rejected'}
        </span>
      </div>
      {item.passage && (
        <blockquote className="evidence-item__quote">
          “{item.passage}”
          <footer>
            {item.page_number ? `Page ${item.page_number}` : 'Abstract'} · quotation · found by{' '}
            {item.retrieval_method ?? 'unknown'}
          </footer>
        </blockquote>
      )}
      {!verified && failed.length > 0 && (
        <p className="field-error">Failed checks: {failed.map((c) => c.details).join('; ')}</p>
      )}
    </li>
  )
}
