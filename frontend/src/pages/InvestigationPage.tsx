import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Circle, FileText, Loader, XCircle } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import type { InvestigationTask, TaskStatus } from '../api/types'
import { BackLink } from '../components/BackLink'
import { ErrorState, LoadingState } from '../components/QueryState'
import { InfoTip } from '../components/InfoTip'
import { StageStepper } from '../features/investigations/StageStepper'
import { StatusBadge } from '../components/StatusBadge'
import { EvidencePreview } from '../features/evidence/EvidencePreview'
import {
  useDiscoveredPapers,
  useEvidence,
  useInvestigation,
  useInvestigationTasks,
  usePipelineStatus,
} from '../features/investigations/hooks'
import {
  documentDetails,
  evidenceDetails,
  summarizeStage,
  validationSummary,
  type StageSummary,
} from '../features/investigations/stages'
import type { StatusTone } from '../features/investigations/status'
import { PaperResult } from '../features/papers/PaperResult'
import { formatDateTime, formatRelative } from '../lib/format'


const TASK_DISPLAY: Record<TaskStatus, { label: string; tone: StatusTone }> = {
  pending: { label: 'Waiting', tone: 'neutral' },
  running: { label: 'In progress', tone: 'info' },
  succeeded: { label: 'Completed', tone: 'success' },
  failed_retryable: { label: 'Retrying', tone: 'warning' },
  failed_permanent: { label: 'Failed', tone: 'error' },
  skipped: { label: 'Skipped', tone: 'neutral' },
}

// If the oldest unpublished event is older than this, no dispatcher is running.
const STALLED_AFTER_SECONDS = 60

export function InvestigationPage() {
  const { investigationId = '' } = useParams()
  const investigation = useInvestigation(investigationId)
  const tasks = useInvestigationTasks(investigationId, investigation.data?.status)
  const taskList = tasks.data ?? []
  const discovery = taskList.find((task) => task.kind === 'discover_papers')
  const papers = useDiscoveredPapers(investigationId, discovery?.status === 'succeeded')
  const pipeline = usePipelineStatus(discovery?.status === 'pending')
  const extraction = summarizeStage(taskList, 'extract_evidence')
  const evidence = useEvidence(investigationId, extraction.state === 'active' || extraction.state === 'done')
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
  const documents = summarizeStage(taskList, 'process_document')
  const validation = validationSummary(taskList, extraction)
  const reportedEvidence = (evidence.data ?? []).some((i) => i.passage !== null)
  const reportTask = taskList.find((task) => task.kind === 'build_report')
  const reportStage: StageSummary = reportTask
    ? {
        ...summarizeStage(taskList, 'build_report'),
        details:
          reportTask.status === 'succeeded'
            ? [`Version ${String(reportTask.result_summary?.version ?? 1)} · ${String(reportTask.result_summary?.findings ?? '')} key findings`]
            : [],
      }
    : { label: 'Waiting', tone: 'neutral', state: validation.state === 'done' ? 'active' : 'waiting', details: [] }

  const stages = [
    { name: 'Discovering relevant papers', short: 'Discover', summary: discoverySummary(discovery, tasks.isPending) },
    {
      name: 'Downloading and processing papers',
      short: 'Read',
      summary: { ...documents, details: [...documents.details, ...documentDetails(taskList)] },
    },
    {
      name: 'Extracting evidence',
      short: 'Extract',
      summary: { ...extraction, details: [...extraction.details, ...evidenceDetails(taskList)] },
    },
    { name: 'Validating findings', short: 'Validate', summary: validation },
    { name: 'Comparing results and writing the report', short: 'Report', summary: reportStage },
  ]

  return (
    <div className="page">
      <BackLink to="/app/investigations">Back to investigations</BackLink>
      <header className="page-header">
        <div>
          <div className="title-row">
            <h1 className="page-title">{data.question}</h1>
            <StatusBadge status={data.status} />
            {data.status === 'queued' && <InfoTip term="queued" label="Queued" />}
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
          <p className="hint stages-intro">
            PaperPilot works through five steps for each question. This page updates by itself; you can leave it
            open or come back later.
          </p>
          <StageStepper stages={stages.map(({ short, summary }) => ({ name: short, state: summary.state, tone: summary.tone }))} />
          <ol className="stage-list">
            {stages.map((stage) => (
              <StageRow key={stage.name} name={stage.name} summary={stage.summary} />
            ))}
          </ol>
          {reportTask?.status === 'succeeded' && (
            <Link to={`/app/investigations/${data.id}/report`} className="button button--primary report-link">
              <FileText aria-hidden="true" size={16} /> View report
            </Link>
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

      {reportedEvidence && evidence.data && (
        <section className="card" aria-labelledby="evidence-heading">
          <div className="card__header">
            <h2 id="evidence-heading" className="card__title">
              Extracted evidence
            </h2>
            <p className="results__source">Exact quotations from each paper, checked against the source text</p>
          </div>
          <EvidencePreview items={evidence.data} />
        </section>
      )}

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

const STATE_ICON = {
  done: CheckCircle2,
  failed: XCircle,
  active: Loader,
  waiting: Circle,
  none: Circle,
}

function StageRow({ name, summary }: { name: string; summary: StageSummary }) {
  const Icon = STATE_ICON[summary.state]
  return (
    <li className="stage-list__item">
      <Icon className={`stage-list__icon stage-list__icon--${summary.tone}`} aria-hidden="true" size={20} />
      <span className="stage-list__name">
        {name}
        {summary.details.map((detail) => (
          <span key={detail} className="stage-list__detail">
            {detail}
          </span>
        ))}
      </span>
      <span className={`status-badge status-badge--${summary.tone}`}>{summary.label}</span>
    </li>
  )
}

function discoverySummary(task: InvestigationTask | undefined, loading: boolean): StageSummary {
  if (loading) return { label: 'Loading', tone: 'neutral', state: 'none', details: [] }
  if (!task) {
    return { label: 'Not started (created before the pipeline)', tone: 'neutral', state: 'none', details: [] }
  }
  const { label, tone } = TASK_DISPLAY[task.status]
  const linked = task.result_summary?.papers_linked
  const details = [
    ...(typeof linked === 'number' ? [`${linked} papers found`] : []),
    ...(task.last_error ? [task.last_error] : []),
    ...(task.attempts > 1 ? [`Attempt ${task.attempts}`] : []),
  ]
  const state =
    task.status === 'succeeded'
      ? 'done'
      : task.status === 'failed_permanent'
        ? 'failed'
        : task.status === 'running'
          ? 'active'
          : 'waiting'
  return { label, tone, state, details }
}

/** Investigation status, papers, and evidence change when tasks do; refetch them then. */
function useRefreshWhenTasksChange(id: string, tasks?: InvestigationTask[]) {
  const queryClient = useQueryClient()
  const signature = tasks?.map((task) => `${task.id}:${task.status}`).join(',')
  useEffect(() => {
    if (signature === undefined) return
    for (const part of ['detail', 'papers', 'evidence']) {
      void queryClient.invalidateQueries({ queryKey: ['investigations', part, id] })
    }
  }, [signature, id, queryClient])
}
