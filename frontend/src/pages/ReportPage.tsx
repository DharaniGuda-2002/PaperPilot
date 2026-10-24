import { useRef, useState, type KeyboardEvent } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import type { Report } from '../api/report'
import { BackLink } from '../components/BackLink'
import { ErrorState, LoadingState } from '../components/QueryState'
import { useReport } from '../features/investigations/hooks'
import { ComparisonMatrix } from '../features/report/ComparisonMatrix'
import { EvidenceInspector } from '../features/report/EvidenceInspector'
import { FindingCard } from '../features/report/FindingCard'
import { InfoTip } from '../components/InfoTip'
import { StrengthBadge } from '../features/report/StrengthBadge'
import { StrengthMeter } from '../features/report/StrengthMeter'
import type { GlossaryKey } from '../lib/glossary'
import { formatDateTime } from '../lib/format'
import { safeExternalUrl } from '../lib/safeUrl'

const TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'comparison', label: 'Comparison' },
  { id: 'sources', label: 'Sources' },
] as const
type TabId = (typeof TABS)[number]['id']

export function ReportPage() {
  const { investigationId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { data, isPending, isError, error } = useReport(investigationId)
  const [inspecting, setInspecting] = useState<string | null>(null)
  const view = (TABS.find((t) => t.id === searchParams.get('view'))?.id ?? 'summary') as TabId
  const back = <BackLink to={`/app/investigations/${investigationId}`}>Back to investigation</BackLink>

  if (isPending) return <LoadingState label="Loading report…" />
  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="page">
          {back}
          <section className="card">
            <h1 className="page-title">Report not ready</h1>
            <p className="page-subtitle">
              The report is built once every paper has finished processing. Check the investigation&apos;s progress.
            </p>
          </section>
        </div>
      )
    }
    return <ErrorState error={error} />
  }

  const report = data.content
  return (
    <div className="page report">
      {back}
      <header className="page-header">
        <div>
          <p className="eyebrow">Investigation report · version {data.version}</p>
          <h1 className="page-title">{report.question}</h1>
          <p className="page-subtitle">Generated {formatDateTime(report.generated_at)}</p>
        </div>
      </header>

      <details className="howto">
        <summary>How to read this report</summary>
        <ul>
          <li><strong>Summary</strong> gives the bottom line and the main findings. Open a finding to see its sources.</li>
          <li>Click any highlighted number or citation to see the exact quotation and the page it came from.</li>
          <li><strong>Comparison</strong> shows results side by side. Only results measured the same way are compared.</li>
          <li><strong>Sources</strong> lists every paper and whether its full text or only its abstract was read.</li>
          <li>All numbers are what the papers report. PaperPilot did not re-run any experiment.</li>
        </ul>
      </details>

      <Tabs view={view} onChange={(next) => setSearchParams(next === 'summary' ? {} : { view: next })} />

      <div role="tabpanel" id={`panel-${view}`} aria-labelledby={`tab-${view}`} tabIndex={0}>
        {view === 'summary' && <Summary report={report} onCite={setInspecting} onOpenComparison={() => setSearchParams({ view: 'comparison' })} />}
        {view === 'comparison' && (
          <section className="card">
            <ComparisonMatrix comparison={report.comparison} onCite={setInspecting} />
          </section>
        )}
        {view === 'sources' && <Sources report={report} />}
      </div>

      <EvidenceInspector evidenceId={inspecting} onClose={() => setInspecting(null)} />
    </div>
  )
}

function Tabs({ view, onChange }: { view: TabId; onChange: (id: TabId) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = TABS.findIndex((t) => t.id === view)
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const next = TABS[(index + step + TABS.length) % TABS.length].id
    onChange(next)
    refs.current[next]?.focus()
  }
  return (
    <div role="tablist" aria-label="Report views" className="tabs" onKeyDown={onKeyDown}>
      {TABS.map((tab) => (
        <button
          key={tab.id}
          ref={(el) => {
            refs.current[tab.id] = el
          }}
          id={`tab-${tab.id}`}
          type="button"
          role="tab"
          aria-selected={view === tab.id}
          aria-controls={`panel-${tab.id}`}
          tabIndex={view === tab.id ? 0 : -1}
          className="tabs__tab"
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

function Summary({ report, onCite, onOpenComparison }: { report: Report; onCite: (id: string) => void; onOpenComparison: () => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const titles = Object.fromEntries(report.key_findings.map((f) => [f.id, f.title]))
  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const openRelated = (id: string) => {
    setExpanded((current) => new Set(current).add(id))
    requestAnimationFrame(() => document.getElementById(`finding-${id}`)?.scrollIntoView({ block: 'start' }))
  }
  const scope = report.scope

  return (
    <div className="report-summary">
      <section className="card bottom-line" aria-labelledby="bottom-line-heading">
        <div className="card__header">
          <h2 id="bottom-line-heading" className="card__title">
            Bottom line
          </h2>
          <span className="badge-with-tip">
            <StrengthBadge strength={report.overall_strength} definition={report.strength_definitions[report.overall_strength]} />
            <InfoTip term="strength" label="evidence strength" />
          </span>
        </div>
        <p className="bottom-line__text">{report.bottom_line}</p>
        <StrengthMeter strength={report.overall_strength} definition={report.strength_definitions[report.overall_strength]} />
        <div className="stats" role="list" aria-label="Report scope">
          <Stat value={scope.papers_discovered} label="Papers discovered" />
          <Stat value={scope.full_text} label="Full texts analyzed" />
          <Stat value={scope.abstract_only} label="Abstracts only" tip="abstractOnly" />
          <Stat value={scope.papers_with_evidence} label="Papers with evidence" tip="evidence" />
        </div>
        <p className="hint">
          {scope.selection} <button type="button" className="text-link" onClick={onOpenComparison}>Open the comparison matrix</button>
        </p>
      </section>

      <section className="card" aria-labelledby="findings-heading">
        <h2 id="findings-heading" className="card__title">
          Key findings
        </h2>
        <ol className="findings">
          {report.key_findings.map((finding, index) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              index={index + 1}
              expanded={expanded.has(finding.id)}
              onToggle={() => toggle(finding.id)}
              onCite={onCite}
              onRelated={openRelated}
              titles={titles}
              definitions={report.strength_definitions}
            />
          ))}
        </ol>
        <details className="strength-help">
          <summary>What do the evidence strength labels mean?</summary>
          <dl className="detail-list">
            {Object.entries(report.strength_definitions).map(([level, text]) => (
              <div key={level} className="detail-list__pair">
                <dt>{level[0].toUpperCase() + level.slice(1)}</dt>
                <dd>{text}</dd>
              </div>
            ))}
          </dl>
          <p className="hint">Strength counts checkable sources. It is not a model&apos;s confidence.</p>
        </details>
      </section>

      <section className="card limits" aria-labelledby="limits-heading">
        <h2 id="limits-heading" className="card__title">
          What limits this report
        </h2>
        <ListBlock title="Limitations" items={report.limitations} />
        <ListBlock title="Missing information" items={report.missing_information} />
        <ListBlock title="Unresolved questions" items={report.unresolved_questions} />
        <p className="hint">
          Generated by {report.generator_version} from evidence extracted with {report.versions.extraction}, validated with{' '}
          {report.versions.validation}, compared with {report.versions.comparison}.
        </p>
      </section>
    </div>
  )
}

function Stat({ value, label, tip }: { value: number; label: string; tip?: GlossaryKey }) {
  return (
    <div className="stat" role="listitem">
      <span>
        <span className="stat__value">{value}</span>
        <span className="stat__label">
          {label}
          {tip && <InfoTip term={tip} label={label} />}
        </span>
      </span>
    </div>
  )
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <h3 className="card__subtitle">{title}</h3>
      <ul className="plain-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function Sources({ report }: { report: Report }) {
  return (
    <section className="card" aria-labelledby="sources-heading">
      <h2 id="sources-heading" className="card__title">
        Sources ({report.papers.length})
      </h2>
      <ol className="sources">
        {report.papers.map((paper) => {
          const doi = paper.doi ? safeExternalUrl(`https://doi.org/${paper.doi}`) : null
          const url = safeExternalUrl(paper.url)
          return (
            <li key={paper.paper_id}>
              <span className="study-list__title">{paper.title}</span>
              <span className="hint">
                {paper.authors.slice(0, 4).join(', ')}
                {paper.authors.length > 4 && ' et al.'}
                {paper.year && ` · ${paper.year}`}
                {paper.venue && ` · ${paper.venue}`}
                {' · '}
                {paper.content_kind === 'full_text' ? 'full text analyzed' : paper.content_kind === 'abstract' ? 'abstract only' : 'no text'}
              </span>
              <span className="link-row">
                {doi && (
                  <a href={doi} target="_blank" rel="noopener noreferrer" className="text-link">
                    DOI {paper.doi}
                  </a>
                )}
                {url && (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="text-link">
                    Source
                  </a>
                )}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
