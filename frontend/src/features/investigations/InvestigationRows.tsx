import { ChevronRight, FileText } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { Investigation } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime, formatRelative } from '../../lib/format'
import { STATUS_DISPLAY } from './status'

export function InvestigationRows({ items }: { items: Investigation[] }) {
  return (
    <ul className="investigation-rows">
      {items.map((investigation) => (
        <li key={investigation.id}>
          <Link to={`/app/investigations/${investigation.id}`} className="investigation-row">
            <span
              className={`icon-tile icon-tile--${STATUS_DISPLAY[investigation.status].tone}`}
              aria-hidden="true"
            >
              <FileText size={18} />
            </span>
            <span className="investigation-row__body">
              <span className="investigation-row__title">{investigation.question}</span>
              <span className="investigation-row__meta">
                Created{' '}
                <time dateTime={investigation.created_at} title={formatDateTime(investigation.created_at)}>
                  {formatRelative(investigation.created_at)}
                </time>
              </span>
            </span>
            <StatusBadge status={investigation.status} />
            <ChevronRight className="investigation-row__chevron" aria-hidden="true" size={18} />
          </Link>
        </li>
      ))}
    </ul>
  )
}
