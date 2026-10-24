import { FileCheck2, FileSearch, Quote, Search } from 'lucide-react'
import { Link } from 'react-router-dom'

import { QuickStartForm } from '../features/investigations/QuickStartForm'

const STEPS = [
  { icon: Search, title: 'Ask', text: 'Type a technical research question in plain English.' },
  { icon: FileSearch, title: 'Find and read', text: 'PaperPilot finds up to 25 relevant papers and reads the free ones.' },
  { icon: Quote, title: 'Extract facts', text: 'It pulls out datasets, results and limitations, each with the exact sentence and page.' },
  { icon: FileCheck2, title: 'Get a report', text: 'You get a short summary, how strong the evidence is, and what is missing.' },
]

const GOOD_AT = [
  'Showing where every fact comes from, so you can check it yourself.',
  'Saying clearly when something was not found, instead of guessing.',
  'Warning you when results cannot be fairly compared.',
]

const NOT_FOR = [
  'Proving that a method works. It reports what papers claim.',
  'Ranking methods as best or worst.',
  'Private or confidential questions. Investigations are public.',
]

export function LandingPage() {
  return (
    <main id="main" tabIndex={-1}>
      <section className="hero">
        <div className="hero__copy">
          <h1 className="display">
            Ask a research question. <span className="display__accent">Get answers you can check.</span>
          </h1>
          <p className="hero__lead">
            PaperPilot reads research papers for you and shows what they report, with the exact quote and page
            behind every fact.
          </p>
          <QuickStartForm label="Research question" placeholder="e.g. Do graph neural networks beat gradient boosting for fraud detection?" />
          <p className="notice notice--info hero__preview">
            <strong>About this public demo:</strong> it saves your question, but the background workers that read
            the papers run only on a local install, so the investigation will stay &quot;Queued&quot;.{' '}
            <Link to="/faq" className="text-link">
              Why, and how to see a full result
            </Link>
            .
          </p>
        </div>

        <div className="hero__visual" id="how-it-works">
          <section className="stage-card" aria-labelledby="how-heading">
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
        </div>
      </section>

      <section className="expect" aria-label="What to expect">
        <div className="expect__col">
          <h2>What it is good at</h2>
          <ul>
            {GOOD_AT.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="expect__col">
          <h2>What it is not for</h2>
          <ul>
            {NOT_FOR.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>

      <p className="landing__more">
        New here? Read the <Link to="/faq">questions and answers</Link> or <Link to="/about">who built this</Link>.
      </p>
    </main>
  )
}
