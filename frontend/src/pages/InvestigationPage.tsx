import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Circle, Loader, XCircle } from 'lucide-react'
import { useEffect } from 'react'
import { useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import type { InvestigationTask, TaskStatus } from '../api/types'
import { BackLink } from '../components/BackLink'
import { ErrorState, LoadingState } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import {
  useDiscoveredPapers,
  useInvestigation,
  useInvestigationTasks,
  usePipelineStatus,
} from '../features/investigations/hooks'
import type { StatusTone } from '../features/investigations/status'
import { PaperResult } from '../features/papers/PaperResult'
import { formatDateTime, formatRelative } from '../lib/format'

// Stages not built yet, with the milestone that adds each one.
const LATER_STAGES = [
  { name: 'Downloading and processing papers', milestone: 'M5' },
  { name: 'Extracting evidence', milestone: 'M5' },
  { name: 'Validating findings', milestone: 'M5' },
  { name: 'Generating comparison', milestone: 'M6' },
  { name: 'Creating final report', milestone: 'M6' },
]

const TASK_DISPLAY: Record<TaskStatus, { label: string; tone: StatusTone }> = {
  pending: { label: 'Waiting', tone: 'neutral' },
  running: { label: 'In progress', tone: 'info' },
  succeeded: { label: 'Completed', tone: 'success' },
  failed_retryable: { label: 'Failed (temporary)', tone: 'error' },
  failed_permanent: { label: 'Failed', tone: 'error' },
  skipped: { label: 'Skipped', tone: 'neutral' },
}

// If the oldest unpublished event is older than this, no dispatcher is running.
const STALLED_AFTER_SECONDS = 60

export function InvestigationPage() {
  const { investigationId = '' } = useParams()
  const investigation = useInvestigation(investigationId)
  const tasks = useInvestigationTasks(investigationId)
  const discovery = tasks.data?.find((task) => task.kind === 'discover_papers')
  const papers = useDiscoveredPapers(investigationId, discovery?.status === 'succeeded')
  const pipeline = usePipelineStatus(discovery?.status === 'pending')
  useRefreshWhenTasksChange(investigationId, tasks.data)

  if (investigation.isPending) return <LoadingState label="Loading investigation…" />
  if (investigation.isError) {
    const error = investigation.error
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

  const data = investigation.data
  const stalled =
    discovery?.status === 'pending' &&
    (pipeline.data?.oldest_pending_seconds ?? 0) > STALLED_AFTER_SECONDS

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
          {stalled && (
            <p className="notice notice--warning" role="status">
              Waiting for a background worker. This deployment is not processing events; the full
              pipeline runs in the local Docker setup.
            </p>
          )}
          <ol className="stage-list">
            <DiscoveryStage task={discovery} loading={tasks.isPending} />
            {LATER_STAGES.map((stage) => (
              <li key={stage.name} className="stage-list__item">
                <Circle className="stage-list__icon" aria-hidden="true" size={20} />
                <span className="stage-list__name">{stage.name}</span>
                <span className="status-badge status-badge--neutral">
                  Not built yet · {stage.milestone}
                </span>
              </li>
            ))}
          </ol>
          {discovery?.status === 'succeeded' && (
            <p className="hint">
              The pipeline currently stops after discovery, so this investigation stays in progress
              until evidence extraction is built.
            </p>
          )}
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

      {discovery?.status === 'succeeded' && (
        <section className="card" aria-labelledby="papers-heading">
          <div className="card__header">
            <h2 id="papers-heading" className="card__title">
              Discovered papers
            </h2>
            {papers.data && (
              <p className="results__source">
                Top {papers.data.total} by relevance
                {typeof discovery.result_summary?.papers_available === 'number' &&
                  ` of ${discovery.result_summary.papers_available.toLocaleString()} matches`}{' '}
                in OpenAlex
              </p>
            )}
          </div>
          {papers.isPending ? (
            <LoadingState label="Loading discovered papers…" />
          ) : papers.isError ? (
            <ErrorState error={papers.error} />
          ) : (
            <ol className="paper-results">
              {papers.data.items.map(({ rank, paper }) => (
                <li key={paper.id} value={rank}>
                  <PaperResult paper={paper} />
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  )
}

function DiscoveryStage({ task, loading }: { task?: InvestigationTask; loading: boolean }) {
  const name = 'Discovering relevant papers'
  if (loading) {
    return (
      <li className="stage-list__item">
        <Circle className="stage-list__icon" aria-hidden="true" size={20} />
        <span className="stage-list__name">{name}</span>
        <span className="status-badge status-badge--neutral">Loading</span>
      </li>
    )
  }
  if (!task) {
    return (
      <li className="stage-list__item">
        <Circle className="stage-list__icon" aria-hidden="true" size={20} />
        <span className="stage-list__name">{name}</span>
        <span className="status-badge status-badge--neutral">Not started (created before the pipeline)</span>
      </li>
    )
  }

  const { label, tone } = TASK_DISPLAY[task.status]
  const Icon =
    task.status === 'succeeded'
      ? CheckCircle2
      : task.status.startsWith('failed')
        ? XCircle
        : task.status === 'running'
          ? Loader
          : Circle
  const linked = task.result_summary?.papers_linked
  return (
    <li className="stage-list__item">
      <Icon className={`stage-list__icon stage-list__icon--${tone}`} aria-hidden="true" size={20} />
      <span className="stage-list__name">
        {name}
        {typeof linked === 'number' && <span className="stage-list__detail">{linked} papers found</span>}
        {task.last_error && <span className="stage-list__detail stage-list__detail--error">{task.last_error}</span>}
        {task.attempts > 1 && <span className="stage-list__detail">Attempt {task.attempts}</span>}
      </span>
      <span className={`status-badge status-badge--${tone}`}>{label}</span>
    </li>
  )
}

/** Investigation status and papers change when tasks do; refetch them then. */
function useRefreshWhenTasksChange(id: string, tasks?: InvestigationTask[]) {
  const queryClient = useQueryClient()
  const signature = tasks?.map((task) => `${task.id}:${task.status}`).join(',')
  useEffect(() => {
    if (signature === undefined) return
    void queryClient.invalidateQueries({ queryKey: ['investigations', 'detail', id] })
    void queryClient.invalidateQueries({ queryKey: ['investigations', 'papers', id] })
  }, [signature, id, queryClient])
}
