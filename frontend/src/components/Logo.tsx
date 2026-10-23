import { BookOpen } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Logo({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="logo">
      <BookOpen aria-hidden="true" size={22} strokeWidth={2.2} />
      <span>PaperPilot</span>
    </Link>
  )
}
