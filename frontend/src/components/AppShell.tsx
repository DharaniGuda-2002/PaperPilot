import { FileSearch, HelpCircle, Home, Info, Search } from 'lucide-react'
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
        <nav aria-label="Help" className="sidebar__nav sidebar__nav--help">
          <NavLink to="/faq" className="sidebar__link">
            <HelpCircle aria-hidden="true" size={18} />
            Questions (FAQ)
          </NavLink>
          <NavLink to="/about" className="sidebar__link">
            <Info aria-hidden="true" size={18} />
            About
          </NavLink>
        </nav>
        <p className="sidebar__note">
          Every fact links to its exact quote. On the public demo, new investigations stay &quot;Queued&quot;
          because the analysis workers run only on a local install.
        </p>
      </aside>
      <main id="main" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
