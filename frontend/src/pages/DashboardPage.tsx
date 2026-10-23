import { CheckCircle2, Clock3, FileSearch, Loader, Plus } from 'lucide-react'
import type { ComponentType } from 'react'
import { Link } from 'react-router-dom'

import { ErrorState, LoadingState } from '../components/QueryState'
import { useInvestigationList, useInvestigationStats } from '../features/investigations/hooks'
import { InvestigationRows } from '../features/investigations/InvestigationRows'
import { QuickStartForm } from '../features/investigations/QuickStartForm'
import type { StatusTone } from '../features/investigations/status'

export function DashboardPage() {
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Your research workspace</h1>
          <p className="page-subtitle">Start an investigation or continue where you left off.</p>
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
      <StatCard icon={FileSearch} tone="info" value={data.total} label="Investigations" />
      <StatCard icon={Clock3} tone="neutral" value={s.queued} label="Queued" />
      <StatCard icon={Loader} tone="warning" value={s.running} label="In progress" />
      <StatCard
        icon={CheckCircle2}
        tone="success"
        value={s.completed + s.partially_completed}
        label="Completed"
      />
    </div>
  )
}

function StatCard(props: {
  icon: ComponentType<{ size?: number }>
  tone: StatusTone
  value: number
  label: string
}) {
  const { icon: Icon, tone, value, label } = props
  return (
    <div className="stat" role="listitem">
      <span className={`icon-tile icon-tile--${tone}`} aria-hidden="true">
        <Icon size={18} />
      </span>
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
