import { ExternalLink, FileText, Quote } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { Paper } from '../../api/types'
import { safeExternalUrl } from '../../lib/safeUrl'
import { AvailabilityBadge } from './AvailabilityBadge'
import { formatAuthors, formatPublication } from './display'

export function PaperResult({ paper }: { paper: Paper }) {
  const pdfUrl = safeExternalUrl(paper.pdf_url)
  const sourceUrl = safeExternalUrl(paper.landing_page_url)

  return (
    <article className="paper-result">
      <div className="paper-result__main">
        <h3 className="paper-result__title">
          <Link to={`/app/papers/${paper.id}`}>{paper.title}</Link>
        </h3>
        <p className="paper-result__meta">
          {formatAuthors(paper.authors)}
          {formatPublication(paper) && <> · {formatPublication(paper)}</>}
        </p>
        {paper.abstract && <p className="paper-result__abstract">{paper.abstract}</p>}
      </div>
      <div className="paper-result__side">
        <AvailabilityBadge value={paper.full_text_availability} />
        {paper.cited_by_count !== null && (
          <span className="paper-result__citations">
            <Quote aria-hidden="true" size={14} />
            {paper.cited_by_count.toLocaleString()} citations
          </span>
        )}
        <span className="paper-result__links">
          {pdfUrl && (
            <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="text-link">
              <FileText aria-hidden="true" size={14} /> PDF
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          )}
          {sourceUrl && (
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-link">
              <ExternalLink aria-hidden="true" size={14} /> Source
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          )}
        </span>
      </div>
    </article>
  )
}
