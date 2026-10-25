import { Code2, Mail } from 'lucide-react'

const REPO_URL = 'https://github.com/DharaniGuda-2002/PaperPilot'
const EMAIL = 'dharaniguda2002@gmail.com'

export function AboutPage() {
  return (
    <main id="main" tabIndex={-1} className="prose">
      <h1 className="display display--page">Research you can trace</h1>
      <p className="prose__lead">Built for careful, source-backed discovery. 
        Reading dozens of papers to answer one technical question takes days. PaperPilot is a
        project that does the first pass: it finds the papers, pulls out what they report with the
        exact quotation and page, and says plainly what it could and could not find.
      </p>

      <section aria-labelledby="principles">
        <h2 id="principles">What it stands for</h2>
        <ul>
          <li>Every fact points to an exact quotation you can check.</li>
          <li>It says &quot;not found&quot; instead of guessing.</li>
          <li>It never ranks methods it cannot compare fairly.</li>
          <li>It runs on free services, with numbers measured and published, including the weak ones.</li>
        </ul>
      </section>

      <section aria-labelledby="built-with">
        <h2 id="built-with">How it is built</h2>
        <p>
          A FastAPI backend with Postgres and pgvector, Kafka workers coordinated through a
          transactional outbox, and a React and TypeScript interface. The full pipeline runs locally
          with Docker Compose; the public site runs the interface and API on free hosting.
        </p>
      </section>

      <section aria-labelledby="author" className="person">
        <h2 id="author">Built by</h2>
        <p className="person__name">Dharani Guda</p>
        <p className="person__role">New graduate in software development and AI systems</p>
        <ul className="person__links">
          <li>
            <Mail aria-hidden="true" size={16} />
            <a href={`mailto:${EMAIL}`}>{EMAIL}</a>
          </li>
          <li>
            <Code2 aria-hidden="true" size={16} />
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
              github.com/DharaniGuda-2002/PaperPilot
            </a>
          </li>
        </ul>
        <p className="hint">Questions, feedback, and opportunities are welcome by email.</p>
      </section>
    </main>
  )
}
