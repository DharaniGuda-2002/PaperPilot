import type { InvestigationTask } from '../../api/types'
import type { StatusTone } from './status'

export interface StageSummary {
  label: string
  tone: StatusTone
  state: 'waiting' | 'active' | 'done' | 'failed' | 'none'
  details: string[]
}

const ACTIVE = new Set(['pending', 'running', 'failed_retryable'])

/** Aggregate the per-paper tasks of one kind into a single stage status. */
export function summarizeStage(tasks: InvestigationTask[], kind: string): StageSummary {
  const ofKind = tasks.filter((task) => task.kind === kind)
  if (ofKind.length === 0) return { label: 'Waiting', tone: 'neutral', state: 'none', details: [] }

  const done = ofKind.filter((t) => t.status === 'succeeded').length
  const failed = ofKind.filter((t) => t.status === 'failed_permanent').length
  const running = ofKind.filter((t) => t.status === 'running').length
  const retrying = ofKind.filter((t) => t.status === 'failed_retryable').length
  const active = ofKind.filter((t) => ACTIVE.has(t.status)).length

  const details = [`${done} of ${ofKind.length} papers done`]
  if (running) details.push(`${running} in progress`)
  if (retrying) details.push(`${retrying} waiting to retry`)
  if (failed) details.push(`${failed} failed`)

  if (active > 0) {
    return { label: done || running ? 'In progress' : 'Waiting', tone: done || running ? 'info' : 'neutral', state: done || running ? 'active' : 'waiting', details }
  }
  if (done === 0) return { label: 'Failed', tone: 'error', state: 'failed', details }
  return {
    label: failed ? 'Completed with failures' : 'Completed',
    tone: failed ? 'warning' : 'success',
    state: 'done',
    details,
  }
}

function sum(tasks: InvestigationTask[], kind: string, key: string): number {
  return tasks
    .filter((t) => t.kind === kind && t.status === 'succeeded')
    .reduce((total, t) => total + (typeof t.result_summary?.[key] === 'number' ? (t.result_summary[key] as number) : 0), 0)
}

export function documentDetails(tasks: InvestigationTask[]): string[] {
  const done = tasks.filter((t) => t.kind === 'process_document' && t.status === 'succeeded')
  const fullText = done.filter((t) => t.result_summary?.content_kind === 'full_text').length
  const abstractOnly = done.filter((t) => t.result_summary?.content_kind === 'abstract').length
  const none = done.filter((t) => t.result_summary?.content_kind === 'none').length
  const parts = []
  if (fullText) parts.push(`${fullText} full text`)
  if (abstractOnly) parts.push(`${abstractOnly} abstract only`)
  if (none) parts.push(`${none} no text`)
  return parts.length ? [parts.join(', ')] : []
}

export function evidenceDetails(tasks: InvestigationTask[]): string[] {
  const records = sum(tasks, 'extract_evidence', 'records')
  return records ? [`${records} facts extracted`] : []
}

export function validationSummary(tasks: InvestigationTask[], extraction: StageSummary): StageSummary {
  const verified = sum(tasks, 'extract_evidence', 'verified')
  const rejected = sum(tasks, 'extract_evidence', 'rejected')
  const details = verified || rejected ? [`${verified} verified, ${rejected} rejected`] : []
  if (extraction.state === 'done') return { label: 'Completed', tone: 'success', state: 'done', details }
  if (extraction.state === 'active') return { label: 'In progress', tone: 'info', state: 'active', details }
  if (extraction.state === 'failed') return { label: 'Failed', tone: 'error', state: 'failed', details }
  return { label: 'Waiting', tone: 'neutral', state: extraction.state, details }
}
