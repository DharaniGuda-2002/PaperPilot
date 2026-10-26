import { CheckCircle2, FileText } from 'lucide-react'

// One real record from data/examples/rag-hallucination.json (evidence 087cf706),
// copied verbatim so the landing page shows what a finished report contains.
const QUOTE_PARTS = [
  'By fusing the results of GAR and DPR in the same way as described in Sec. 3.3, we further obtain consistently higher performance than both methods, with top-100 accuracy ',
  '88.9%',
  ' and top1000 accuracy ',
  '93.2%',
  '.',
]

const CHECKS = ['Quotation found in the paper', 'Page reference matches', 'Numbers appear in the quote']

/** Static preview of an evidence card, built from a real example run. */
export function EvidenceShowcase() {
  return (
    <figure className="showcase" aria-label="Example evidence card from a real report">
      <div className="showcase__back" aria-hidden="true" />
      <div className="showcase__card">
        <div className="showcase__head">
          <span className="showcase__field">Reported result</span>
          <span className="showcase__page">Page 7</span>
        </div>
        <p className="showcase__metric">
          Accuracy <strong>88.9%</strong>
        </p>
        <blockquote className="showcase__quote">
          “
          {QUOTE_PARTS.map((part, index) =>
            index % 2 === 1 ? <mark key={index}>{part}</mark> : <span key={index}>{part}</span>,
          )}
          ”
        </blockquote>
        <ul className="showcase__checks">
          {CHECKS.map((check) => (
            <li key={check}>
              <CheckCircle2 aria-hidden="true" size={16} />
              {check}
            </li>
          ))}
        </ul>
        <div className="showcase__source">
          <FileText aria-hidden="true" size={16} />
          <span>
            <strong>Generation-Augmented Retrieval for Open-Domain Question Answering</strong>
            <span className="showcase__venue">Mao et al. · ACL 2021</span>
          </span>
        </div>
      </div>
      <figcaption className="showcase__caption">A real evidence card from one of the example reports.</figcaption>
    </figure>
  )
}
