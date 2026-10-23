import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section className="card">
      <h1>Page not found</h1>
      <p className="lead">
        <Link to="/">Back to dashboard</Link>
      </p>
    </section>
  )
}
