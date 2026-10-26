import { Link } from 'react-router-dom'

import { EvidenceShowcase } from '../features/evidence/EvidenceShowcase'
import { useExamples } from '../features/investigations/hooks'

const STEPS = [
  { title: 'Ask', text: 'A technical question in plain English.' },
  { title: 'Find and read', text: 'Up to 25 relevant papers, free ones read in full.' },
  { title: 'Extract facts', text: 'Datasets, results and limits, each with its quote and page.' },
  { title: 'Get a report', text: 'A short summary, evidence strength, and what is missing.' },
]

const FEATURES = [
  { title: 'Literature search', text: 'Find up to 25 relevant papers from OpenAlex for your question.' },
  { title: 'Evidence-backed analysis', text: 'Compare findings only where the comparison is fair.' },
  { title: 'Transparent citations', text: 'Trace every conclusion to the exact quote and page.' },
]

export function LandingPage() {
  const example = useExamples().data?.[0]
  return (
    <main id="main" tabIndex={-1}>
      <p className="demo-banner" role="note">
        <strong>Public demo:</strong> questions are saved but not analyzed here.{' '}
        <Link to="/faq" className="text-link">
          Why, and how to see a full result
        </Link>
      </p>

      <section className="hero">
        <div className="hero__copy">
          <h1 className="display">
            Ask a research question. <span className="display__accent">Get answers you can check.</span>
          </h1>
          <p className="hero__lead">
            PaperPilot reads research papers for you and shows what they report, with the exact quote and page
            behind every fact.
          </p>
          <div className="hero__actions">
            <Link to="/app/investigations/new" className="button button--primary button--large">
              Start an investigation
            </Link>
            {example ? (
              <Link
                to={`/app/investigations/${example.id}/report`}
                className="button button--secondary button--large"
              >
                See a finished example
              </Link>
            ) : (
              <Link to="/faq" className="button button--secondary button--large">
                Read the FAQ
              </Link>
            )}
          </div>
        </div>

        <EvidenceShowcase />
      </section>

      <section className="steps" id="how-it-works" aria-labelledby="how-heading">
        <h2 id="how-heading" className="steps__title">
          How it works
        </h2>
        <ol className="steps__list">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <span className="steps__number" aria-hidden="true">
                {index + 1}
              </span>
              <strong>{step.title}</strong>
              <span>{step.text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="feature-cards" aria-label="Capabilities">
        {FEATURES.map((feature) => (
          <div key={feature.title} className="feature-card">
            <h2>{feature.title}</h2>
            <p>{feature.text}</p>
          </div>
        ))}
      </section>
    </main>
  )
}
