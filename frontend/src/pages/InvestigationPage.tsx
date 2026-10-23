import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { ErrorState, LoadingState } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import { useInvestigation } from '../features/investigations/hooks'
import { formatDateTime } from '../lib/format'

export function InvestigationPage() {
  const { investigationId = '' } = useParams()
  const { data, isPending, isError, error } = useInvestigation(investigationId)

  if (isPending) return <LoadingState label="Loading investigation…" />
  if (isError) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return (
        <section className="card">
          <h1>Investigation not found</h1>
          <p className="lead">
            It may have been removed, or the link is wrong. <Link to="/">Back to dashboard</Link>
          </p>
        </section>
      )
    }
    return <ErrorState error={error} />
  }

  return (
    <section className="card" aria-labelledby="investigation-question">
      <p className="muted" style={{ margin: 0 }}>
        Investigation
      </p>
      <h1 id="investigation-question" className="question-title">
        {data.question}
      </h1>
      <dl className="detail-list" style={{ marginTop: 'var(--space-6)' }}>
        <dt>Status</dt>
        <dd>
          <StatusBadge status={data.status} />
        </dd>
        <dt>Created</dt>
        <dd>{formatDateTime(data.created_at)}</dd>
        <dt>Last updated</dt>
        <dd>{formatDateTime(data.updated_at)}</dd>
      </dl>
      <p className="notice notice--info" style={{ marginTop: 'var(--space-6)' }}>
        The processing pipeline is not built yet. This investigation is saved and will stay
        queued until paper discovery is added in a later milestone.
      </p>
    </section>
  )
}
