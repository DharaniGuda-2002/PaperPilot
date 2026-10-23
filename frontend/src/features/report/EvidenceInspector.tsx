import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { ErrorState, LoadingState } from '../../components/QueryState'
import { formatDateTime } from '../../lib/format'
import { safeExternalUrl } from '../../lib/safeUrl'
import { useEvidenceDetail } from '../investigations/hooks'

const CONTENT_KIND: Record<string, string> = {
  full_text: 'Full text (open-access PDF)',
  abstract: 'Abstract only',
  none: 'No text available',
}

const RULES: Record<string, string> = {
  passage_in_source: 'Quotation found in the stored text',
  page_reference: 'Page reference consistent',
  numbers_in_passage: 'Numbers appear in the quotation',
  value_range: 'Value within its scale',
}

/** Level 3: everything behind one citation, in a modal dialog. */
export function EvidenceInspector({ evidenceId, onClose }: { evidenceId: string | null; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const { data, isPending, isError, error } = useEvidenceDetail(evidenceId)

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (evidenceId && !element.open) {
      if (typeof element.showModal === 'function') element.showModal()
      else element.setAttribute('open', '')
    }
    if (!evidenceId && element.open) element.close?.()
  }, [evidenceId])

  const doi = data?.doi ? safeExternalUrl(`https://doi.org/${data.doi}`) : null
  const source = safeExternalUrl(data?.document?.source_url ?? data?.paper_url)

  return (
    <dialog ref={dialog} className="inspector" aria-labelledby="inspector-title" onClose={onClose}>
      <div className="inspector__header">
        <h2 id="inspector-title" className="card__title">
          Evidence inspector
        </h2>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close evidence inspector">
          <X aria-hidden="true" size={18} />
        </button>
      </div>
      {evidenceId === null ? null : isPending ? (
        <LoadingState label="Loading evidence…" />
      ) : isError ? (
        <ErrorState error={error} />
      ) : (
        <div className="inspector__body">
          <section aria-label="Source paper">
            <p className="inspector__paper">{data.paper_title}</p>
            <p className="hint">
              {data.authors.slice(0, 6).join(', ')}
              {data.authors.length > 6 && ' et al.'}
              {[data.year, data.venue].filter(Boolean).length > 0 && ` · ${[data.year, data.venue].filter(Boolean).join(' · ')}`}
            </p>
            <p className="link-row">
              {doi && (
                <a href={doi} target="_blank" rel="noopener noreferrer" className="text-link">
                  DOI {data.doi}
                </a>
              )}
              {source && (
                <a href={source} target="_blank" rel="noopener noreferrer" className="text-link">
                  Source document
                </a>
              )}
            </p>
          </section>

          {data.passage && (
            <figure className="inspector__quote">
              <figcaption>
                {data.passage_kind === 'quotation' ? 'Exact quotation from the paper' : 'Paraphrase (not a quotation)'}
                {' · '}
                {data.page_number ? `page ${data.page_number}` : 'from the abstract (no page)'}
              </figcaption>
              <blockquote>“{data.passage}”</blockquote>
            </figure>
          )}

          <dl className="detail-list">
            <dt>Document</dt>
            <dd>
              {data.document ? CONTENT_KIND[data.document.content_kind] ?? data.document.content_kind : 'Not processed'}
              {data.document?.full_text_unavailable_reason && (
                <span className="hint"> ({data.document.full_text_unavailable_reason})</span>
              )}
            </dd>
            <dt>Extraction</dt>
            <dd>
              {data.extraction_method} · {data.extraction_version}
            </dd>
            <dt>Found by</dt>
            <dd>
              {data.retrieval_method ?? 'unknown'}
              {data.retrieval_score !== null && ` (score ${data.retrieval_score.toFixed(4)})`}
            </dd>
            <dt>Validation</dt>
            <dd>{data.validation_status === 'verified' ? 'Verified' : data.validation_status === 'rejected' ? 'Rejected' : 'Not validated'}</dd>
            <dt>Recorded</dt>
            <dd>{formatDateTime(data.created_at)}</dd>
          </dl>

          {data.checks.length > 0 && (
            <section aria-labelledby="checks-heading">
              <h3 id="checks-heading" className="card__subtitle">
                Validation checks ({data.checks[0].validator_version})
              </h3>
              <ul className="check-list">
                {data.checks.map((check) => (
                  <li key={check.rule}>
                    <span className={`status-badge status-badge--${check.outcome === 'pass' ? 'success' : 'error'}`}>
                      {check.outcome === 'pass' ? 'Pass' : 'Fail'}
                    </span>{' '}
                    {RULES[check.rule] ?? check.rule}
                    {check.details && <span className="hint"> — {check.details}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </dialog>
  )
}
