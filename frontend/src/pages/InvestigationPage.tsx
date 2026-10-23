import { Circle } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { BackLink } from '../components/BackLink'
import { ErrorState, LoadingState } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import { useInvestigation } from '../features/investigations/hooks'
import { formatDateTime, formatRelative } from '../lib/format'

// Planned pipeline stages and the milestone that builds each one.
const STAGES = [
  { name: 'Discovering relevant papers', milestone: 'M2' },
  { name: 'Downloading and processing papers', milestone: 'M5' },
  { name: 'Extracting evidence', milestone: 'M5' },
  { name: 'Validating findings', milestone: 'M5' },
  { name: 'Generating comparison', milestone: 'M6' },
  { name: 'Creating final report', milestone: 'M6' },
]

export function InvestigationPage() {
  const { investigationId = '' } = useParams()
  const { data, isPending, isError, error } = useInvestigation(investigationId)

  if (isPending) return <LoadingState label="Loading investigation…" />
  if (isError) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return (
        <div className="page">
          <BackLink to="/app/investigations">Back to investigations</BackLink>
          <section className="card">
            <h1 className="page-title">Investigation not found</h1>
            <p className="page-subtitle">It may have been removed, or the link is wrong.</p>
          </section>
        </div>
      )
    }
    return <ErrorState error={error} />
  }

  return (
    <div className="page">
      <BackLink to="/app/investigations">Back to investigations</BackLink>
      <header className="page-header">
        <div>
          <div className="title-row">
            <h1 className="page-title">{data.question}</h1>
            <StatusBadge status={data.status} />
          </div>
          <p className="page-subtitle">
            Created{' '}
            <time dateTime={data.created_at} title={formatDateTime(data.created_at)}>
              {formatRelative(data.created_at)}
            </time>
          </p>
        </div>
      </header>

      <div className="two-column">
        <section className="card" aria-labelledby="stages-heading">
          <h2 id="stages-heading" className="card__title">
            Processing stages
          </h2>
          <p className="notice notice--info">
            The processing pipeline is not built yet. This investigation is saved and will stay
            queued until paper discovery is added.
          </p>
          <ol className="stage-list">
            {STAGES.map((stage) => (
              <li key={stage.name} className="stage-list__item">
                <Circle className="stage-list__icon" aria-hidden="true" size={20} />
                <span className="stage-list__name">{stage.name}</span>
                <span className="status-badge status-badge--neutral">
                  Not built yet · {stage.milestone}
                </span>
              </li>
            ))}
          </ol>
        </section>

        <section className="card" aria-labelledby="details-heading">
          <h2 id="details-heading" className="card__title">
            Details
          </h2>
          <dl className="detail-list">
            <dt>Status</dt>
            <dd>
              <StatusBadge status={data.status} />
            </dd>
            <dt>Created</dt>
            <dd>{formatDateTime(data.created_at)}</dd>
            <dt>Last updated</dt>
            <dd>{formatDateTime(data.updated_at)}</dd>
            <dt>ID</dt>
            <dd className="mono">{data.id}</dd>
          </dl>
        </section>
      </div>
    </div>
  )
}
