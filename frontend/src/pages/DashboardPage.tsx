import { QuestionForm } from '../features/investigations/QuestionForm'
import { RecentInvestigations } from '../features/investigations/RecentInvestigations'

export function DashboardPage() {
  return (
    <>
      <section className="card" aria-labelledby="new-investigation">
        <h1 id="new-investigation">Start a research investigation</h1>
        <p className="lead">
          PaperPilot will find relevant papers, extract reported evidence, and show where every
          finding comes from.
        </p>
        <div style={{ marginTop: 'var(--space-6)' }}>
          <QuestionForm />
        </div>
      </section>
      <section className="card" aria-labelledby="recent-investigations">
        <h2 id="recent-investigations">Recent investigations</h2>
        <RecentInvestigations />
      </section>
    </>
  )
}
