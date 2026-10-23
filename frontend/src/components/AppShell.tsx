import { FileSearch, Home } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { Logo } from './Logo'

const NAV = [
  { to: '/app', label: 'Home', icon: Home, end: true },
  { to: '/app/investigations', label: 'Investigations', icon: FileSearch, end: false },
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
          Early preview. Paper discovery and reports are in development.
        </p>
      </aside>
      <main id="main" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
