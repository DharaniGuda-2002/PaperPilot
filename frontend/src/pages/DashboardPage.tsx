import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ErrorState, LoadingState } from '../components/QueryState'
import { useInvestigationList, useInvestigationStats } from '../features/investigations/hooks'
import { InvestigationRows } from '../features/investigations/InvestigationRows'
import { QuickStartForm } from '../features/investigations/QuickStartForm'

export function DashboardPage() {
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Welcome to PaperPilot</h1>
          <p className="page-subtitle">Ask a research question, then review the evidence behind every finding.</p>
        </div>
        <Link to="/app/investigations/new" className="button button--primary">
          <Plus aria-hidden="true" size={16} /> New investigation
        </Link>
      </header>

      <StatsRow />

      <section className="card" aria-labelledby="start-heading">
        <h2 id="start-heading" className="card__title">
          Start a new investigation
        </h2>
        <QuickStartForm label="What would you like to investigate?" placeholder="What would you like to investigate?" />
      </section>

      <section className="card" aria-labelledby="recent-heading">
        <div className="card__header">
          <h2 id="recent-heading" className="card__title">
            Recent investigations
          </h2>
          <Link to="/app/investigations" className="text-link">
            View all
          </Link>
        </div>
        <RecentInvestigations />
      </section>
    </div>
  )
}

function StatsRow() {
  const { data, isPending, isError, error } = useInvestigationStats()
  if (isPending) return <LoadingState label="Loading summary…" />
  if (isError) return <ErrorState error={error} />

  const s = data.by_status
  return (
    <div className="stats" role="list" aria-label="Investigation summary">
      <StatCard value={data.total} label="Investigations" />
      <StatCard value={s.queued} label="Queued" />
      <StatCard value={s.running} label="In progress" />
      <StatCard value={s.completed + s.partially_completed} label="Completed" />
    </div>
  )
}

function StatCard({ value, label }: { value: number; label: string }) {
  return (
    <div className="stat" role="listitem">
      <span>
        <span className="stat__value">{value}</span>
        <span className="stat__label">{label}</span>
      </span>
    </div>
  )
}

function RecentInvestigations() {
  const { data, isPending, isError, error } = useInvestigationList(5)
  if (isPending) return <LoadingState label="Loading recent investigations…" />
  if (isError) return <ErrorState error={error} />
  if (data.items.length === 0) {
    return <p className="empty">No investigations yet. Ask a research question to start one.</p>
  }
  return <InvestigationRows items={data.items} />
}
