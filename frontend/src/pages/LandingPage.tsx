import { BarChart3, FileCheck2, FileSearch, Search, Timer } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Logo } from '../components/Logo'
import { QuickStartForm } from '../features/investigations/QuickStartForm'

const STAGES = [
  'Discover relevant papers',
  'Extract key findings with source passages',
  'Compare methods and evaluation settings',
  'Generate an evidence-backed report',
]

const FEATURES = [
  { icon: Search, title: 'Paper discovery', text: 'Find relevant open research for your question.' },
  { icon: FileSearch, title: 'Structured extraction', text: 'Pull out methods, datasets, metrics, and results.' },
  { icon: FileCheck2, title: 'Evidence-backed reports', text: 'Trace every finding to its source passage.' },
  { icon: Timer, title: 'Transparent processing', text: 'See each stage, retry, and failure as it happens.' },
]

const ROADMAP_URL = 'https://github.com/DharaniGuda-2002/PaperPilot/blob/main/docs/roadmap.md'

export function LandingPage() {
  return (
    <div className="landing">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="landing__header">
        <Logo />
        <nav aria-label="Site" className="landing__nav">
          <a href="#how-it-works">How it works</a>
          <a href={ROADMAP_URL} target="_blank" rel="noreferrer">
            Roadmap
          </a>
        </nav>
        <Link to="/app" className="button button--primary">
          Open app
        </Link>
      </header>

      <main id="main" tabIndex={-1}>
        <section className="hero">
          <div className="hero__copy">
            <h1 className="display">
              Turn research papers into <span className="display__accent">clear insights.</span>
            </h1>
            <p className="hero__lead">
              Ask a technical research question. PaperPilot discovers relevant literature, extracts
              reported evidence, and shows exactly where every finding comes from.
            </p>
            <QuickStartForm label="Research question" placeholder="Ask a research question…" />
            <p className="notice notice--info hero__preview">
              Evidence is extracted by deterministic rules and checked against the source text.
              Reports summarize what papers report; they never rank methods. The hosted demo runs
              no background workers, so its investigations stay queued; the full pipeline runs
              locally with Docker Compose.
            </p>
          </div>

          <div className="hero__visual" id="how-it-works">
            <div className="paper-stack" aria-hidden="true">
              <span />
              <span />
            </div>
            <section className="stage-card" aria-labelledby="how-heading">
              <h2 id="how-heading" className="stage-card__title">
                <BarChart3 aria-hidden="true" size={18} /> How an investigation runs
              </h2>
              <ol className="stage-card__list">
                {STAGES.map((stage, index) => (
                  <li key={stage}>
                    <span className="stage-card__step">{index + 1}</span>
                    {stage}
                  </li>
                ))}
              </ol>
            </section>
          </div>
        </section>

        <section className="features" aria-label="Capabilities">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="feature">
              <span className="feature__icon" aria-hidden="true">
                <Icon size={20} />
              </span>
              <h2 className="feature__title">{title}</h2>
              <p className="feature__text">{text}</p>
            </div>
          ))}
        </section>
      </main>
    </div>
  )
}
