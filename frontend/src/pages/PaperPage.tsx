import { ExternalLink, FileText } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { BackLink } from '../components/BackLink'
import { ErrorState, LoadingState } from '../components/QueryState'
import { AvailabilityBadge } from '../features/papers/AvailabilityBadge'
import { usePaper } from '../features/papers/hooks'
import { formatDateTime } from '../lib/format'
import { safeExternalUrl } from '../lib/safeUrl'

export function PaperPage() {
  const { paperId = '' } = useParams()
  const { data, isPending, isError, error } = usePaper(paperId)

  if (isPending) return <LoadingState label="Loading paper…" />
  if (isError) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return (
        <div className="page">
          <BackLink to="/app/search">Back to search</BackLink>
          <section className="card">
            <h1 className="page-title">Paper not found</h1>
          </section>
        </div>
      )
    }
    return <ErrorState error={error} />
  }

  const pdfUrl = safeExternalUrl(data.pdf_url)
  const sourceUrl = safeExternalUrl(data.landing_page_url)
  const doiUrl = data.doi ? safeExternalUrl(`https://doi.org/${data.doi}`) : null

  return (
    <div className="page">
      <BackLink to="/app/search">Back to search</BackLink>
      <header className="page-header">
        <div>
          <h1 className="page-title">{data.title}</h1>
          <p className="page-subtitle">{data.authors.join(', ') || 'Unknown authors'}</p>
        </div>
      </header>

      <div className="two-column">
        <section className="card" aria-labelledby="abstract-heading">
          <h2 id="abstract-heading" className="card__title">
            Abstract
          </h2>
          {data.abstract ? (
            <>
              <p className="reading">{data.abstract}</p>
              <p className="hint">
                Abstract text as provided by OpenAlex. PaperPilot has not analyzed this paper yet.
              </p>
            </>
          ) : (
            <p className="empty">OpenAlex does not provide an abstract for this paper.</p>
          )}
          <div className="link-row">
            {pdfUrl && (
              <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="button button--primary">
                <FileText aria-hidden="true" size={16} /> Open PDF
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
            )}
            {sourceUrl && (
              <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="button button--secondary">
                <ExternalLink aria-hidden="true" size={16} /> Publisher page
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
            )}
          </div>
        </section>

        <section className="card" aria-labelledby="details-heading">
          <h2 id="details-heading" className="card__title">
            Details
          </h2>
          <dl className="detail-list">
            <dt>Full text</dt>
            <dd>
              <AvailabilityBadge value={data.full_text_availability} />
            </dd>
            <dt>Year</dt>
            <dd>{data.publication_year ?? 'Unknown'}</dd>
            <dt>Venue</dt>
            <dd>{data.venue ?? 'Unknown'}</dd>
            <dt>Type</dt>
            <dd>{data.work_type ?? 'Unknown'}</dd>
            <dt>Citations</dt>
            <dd>{data.cited_by_count?.toLocaleString() ?? 'Unknown'}</dd>
            <dt>License</dt>
            <dd>{data.license ?? 'Not stated'}</dd>
            <dt>DOI</dt>
            <dd>
              {doiUrl ? (
                <a href={doiUrl} target="_blank" rel="noopener noreferrer" className="mono">
                  {data.doi}
                </a>
              ) : (
                'None'
              )}
            </dd>
          </dl>
          <h3 className="card__subtitle">Provenance</h3>
          <dl className="detail-list">
            <dt>Source</dt>
            <dd>
              {data.provider === 'openalex' ? 'OpenAlex' : data.provider}{' '}
              <span className="mono">{data.provider_id}</span>
            </dd>
            <dt>Retrieved</dt>
            <dd>{formatDateTime(data.metadata_fetched_at)}</dd>
          </dl>
        </section>
      </div>
    </div>
  )
}
