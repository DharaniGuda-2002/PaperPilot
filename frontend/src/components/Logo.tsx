import { Link } from 'react-router-dom'

export function Logo({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="logo">
      <span className="logo__mark" aria-hidden="true">
        ✦
      </span>
      <span>PaperPilot</span>
    </Link>
  )
}
