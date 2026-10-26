import { Code2, FileCheck2, Mail, Quote, Scale, Wallet } from 'lucide-react'

const REPO_URL = 'https://github.com/DharaniGuda-2002/PaperPilot'
const EMAIL = 'dharaniguda2002@gmail.com'

const PRINCIPLES = [
  { icon: Quote, title: 'Every fact is quoted', text: 'Each finding links to the exact sentence and page it came from.' },
  { icon: FileCheck2, title: 'Says "not found"', text: 'When the text does not say something, PaperPilot reports that instead of guessing.' },
  { icon: Scale, title: 'Fair comparisons only', text: 'Results are compared only when the metric, dataset and test setup match.' },
  { icon: Wallet, title: 'Free and measured', text: 'Runs on free tiers, with accuracy and speed published, including the weak numbers.' },
]

const STACK = ['FastAPI', 'PostgreSQL + pgvector', 'Kafka', 'Transactional outbox', 'React', 'TypeScript', 'Docker Compose']

export function AboutPage() {
  return (
    <main id="main" tabIndex={-1} className="about">
      <header className="about__intro">
        <p className="eyebrow">About PaperPilot</p>
        <h1 className="display display--page">Research you can trace</h1>
        <p className="prose__lead">
          Answering one technical question can mean reading dozens of papers. PaperPilot does the first pass: it
          finds the papers, pulls out what they report with the exact quote and page, and says plainly what it could
          not find.
        </p>
      </header>

      <section className="about__principles" aria-label="What PaperPilot stands for">
        {PRINCIPLES.map(({ icon: Icon, title, text }) => (
          <div key={title} className="about-card">
            <span className="about-card__icon" aria-hidden="true">
              <Icon size={20} />
            </span>
            <h2>{title}</h2>
            <p>{text}</p>
          </div>
        ))}
      </section>

      <div className="about__split">
        <section className="about-panel" aria-labelledby="built-with">
          <h2 id="built-with">How it is built</h2>
          <p>
            An API and background workers share one database. Workers find papers, read open-access PDFs, extract
            evidence with fixed rules, check every quotation, and write the report. The full pipeline runs locally;
            the public site runs the interface and API on free hosting.
          </p>
          <ul className="stack-chips" aria-label="Technology">
            {STACK.map((item) => (
              <li key={item} className="chip chip--static">
                {item}
              </li>
            ))}
          </ul>
        </section>

        <section className="about-panel profile" aria-labelledby="author">
          <h2 id="author" className="visually-hidden">
            Built by
          </h2>
          <div className="profile__head">
            <span className="profile__avatar" aria-hidden="true">
              DG
            </span>
            <div>
              <p className="profile__name">Dharani Guda</p>
              <p className="profile__role">New graduate in software development and AI systems</p>
            </div>
          </div>
          <p>Built PaperPilot end to end: backend, workers, evaluation, and interface.</p>
          <div className="profile__actions">
            <a href={`mailto:${EMAIL}`} className="button button--primary">
              <Mail aria-hidden="true" size={16} /> Email me
            </a>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="button button--secondary">
              <Code2 aria-hidden="true" size={16} /> Source code
            </a>
          </div>
        </section>
      </div>
    </main>
  )
}
