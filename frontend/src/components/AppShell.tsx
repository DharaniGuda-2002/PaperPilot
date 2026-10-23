import { FileSearch, Home, Search } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { Logo } from './Logo'

const NAV = [
  { to: '/app', label: 'Home', icon: Home, end: true },
  { to: '/app/investigations', label: 'Investigations', icon: FileSearch, end: false },
  { to: '/app/search', label: 'Search', icon: Search, end: false },
]

export function AppShell() {
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <aside className="sidebar">
        <Logo to="/app" />
        <nav aria-label="Main" className="sidebar__nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="sidebar__link">
              <Icon aria-hidden="true" size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="sidebar__note">
          Findings quote their sources. The hosted demo runs no background workers, so its
          investigations stay queued; the full pipeline runs locally.
        </p>
      </aside>
      <main id="main" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
