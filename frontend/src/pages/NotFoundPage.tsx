import { BackLink } from '../components/BackLink'

export function NotFoundPage() {
  return (
    <div className="page">
      <BackLink to="/app">Back to home</BackLink>
      <section className="card">
        <h1 className="page-title">Page not found</h1>
        <p className="page-subtitle">The page you were looking for does not exist.</p>
      </section>
    </div>
  )
}
