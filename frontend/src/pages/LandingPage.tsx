import { Link } from 'react-router-dom'

import { useExamples } from '../features/investigations/hooks'

const STEPS = [
  { title: 'Ask', text: 'Type a technical research question in plain English.' },
  { title: 'Find and read', text: 'PaperPilot finds up to 25 relevant papers and reads the free ones.' },
  { title: 'Extract facts', text: 'It pulls out datasets, results and limitations, each with the exact sentence and page.' },
  { title: 'Get a report', text: 'You get a short summary, how strong the evidence is, and what is missing.' },
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

        <section className="stage-card" id="how-it-works" aria-labelledby="how-heading">
          <h2 id="how-heading" className="stage-card__title">
            How it works
          </h2>
          <ol className="stage-card__list">
            {STEPS.map((step, index) => (
              <li key={step.title}>
                <span className="stage-card__step">{index + 1}</span>
                <span>
                  <strong>{step.title}.</strong> {step.text}
                </span>
              </li>
            ))}
          </ol>
        </section>
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
