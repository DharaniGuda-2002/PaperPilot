import { Link } from 'react-router-dom'

import { BackLink } from '../components/BackLink'

export function NotFoundPage() {
  return (
    <div className="page">
      <BackLink to="/app">Back to home</BackLink>
      <section className="card">
        <h1 className="page-title">Page not found</h1>
        <p className="page-subtitle">
          We couldn&apos;t find that page. The link may be outdated, or the page may have moved.
        </p>
        <p>Return to your dashboard or search for a paper or investigation.</p>
        <p className="form-actions">
          <Link to="/app" className="button button--primary">
            Go to dashboard
          </Link>
          <Link to="/app/search" className="button button--secondary">
            Search papers
          </Link>
        </p>
      </section>
    </div>
  )
}
