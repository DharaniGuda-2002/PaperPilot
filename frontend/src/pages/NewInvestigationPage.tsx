import { BackLink } from '../components/BackLink'
import { QuestionForm } from '../features/investigations/QuestionForm'

export function NewInvestigationPage() {
  return (
    <div className="page page--narrow">
      <BackLink to="/app/investigations">Back to investigations</BackLink>
      <header className="page-header">
        <div>
          <h1 className="page-title">New investigation</h1>
          <p className="page-subtitle">
            Ask a focused question. Get a sourced report.
          </p>
        </div>
      </header>
      <section className="card">
        <QuestionForm />
      </section>
    </div>
  )
}
