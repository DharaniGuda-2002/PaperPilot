import { Link } from 'react-router-dom'

import { ErrorState, LoadingState } from '../../components/QueryState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../lib/format'
import { useRecentInvestigations } from './hooks'

export function RecentInvestigations() {
  const { data, isPending, isError, error } = useRecentInvestigations()

  if (isPending) return <LoadingState label="Loading recent investigations…" />
  if (isError) return <ErrorState error={error} />
  if (data.items.length === 0) {
    return <p className="muted">No investigations yet. Ask a research question to start one.</p>
  }

  return (
    <ul className="investigation-list">
      {data.items.map((investigation) => (
        <li key={investigation.id}>
          <Link to={`/investigations/${investigation.id}`}>
            <span className="investigation-list__question">{investigation.question}</span>
            <StatusBadge status={investigation.status} />
            <span className="investigation-list__meta">
              Created {formatDateTime(investigation.created_at)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
