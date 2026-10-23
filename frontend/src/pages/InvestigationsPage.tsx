import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ErrorState, LoadingState } from '../components/QueryState'
import { useInvestigationList } from '../features/investigations/hooks'
import { InvestigationRows } from '../features/investigations/InvestigationRows'

const PAGE_SIZE = 20

export function InvestigationsPage() {
  const [offset, setOffset] = useState(0)
  const { data, isPending, isError, error, isPlaceholderData } = useInvestigationList(
    PAGE_SIZE,
    offset,
  )

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Investigations</h1>
          <p className="page-subtitle">Every research question you have asked, newest first.</p>
        </div>
        <Link to="/app/investigations/new" className="button button--primary">
          <Plus aria-hidden="true" size={16} /> New investigation
        </Link>
      </header>

      <section className="card" aria-label="All investigations">
        {isPending ? (
          <LoadingState label="Loading investigations…" />
        ) : isError ? (
          <ErrorState error={error} />
        ) : data.items.length === 0 ? (
          <p className="empty">No investigations yet.</p>
        ) : (
          <>
            <InvestigationRows items={data.items} />
            <nav className="pagination" aria-label="Pagination">
              <span className="pagination__summary">
                {offset + 1}–{offset + data.items.length} of {data.total}
              </span>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0 || isPlaceholderData}
              >
                Previous
              </button>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= data.total || isPlaceholderData}
              >
                Next
              </button>
            </nav>
          </>
        )}
      </section>
    </div>
  )
}
