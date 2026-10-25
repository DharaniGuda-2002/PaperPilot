import { Link, NavLink, Outlet } from 'react-router-dom'

import { Logo } from './Logo'

const REPO_URL = 'https://github.com/DharaniGuda-2002/PaperPilot'

/** Header and footer shared by the public pages (home, FAQ, about). */
export function PublicLayout() {
  return (
    <div className="landing">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="landing__header">
        <Logo />
        <nav aria-label="Site" className="landing__nav">
          <Link to="/#how-it-works">How it works</Link>
          <NavLink to="/faq">FAQ</NavLink>
          <NavLink to="/about">About</NavLink>
        </nav>
        <Link to="/app/investigations/new" className="button button--primary">
          Get started
        </Link>
      </header>
      <Outlet />
      <footer className="site-footer">
        <p>
          PaperPilot summarizes what research papers report. It does not prove results or rank methods.
        </p>
        <nav aria-label="Footer">
          <Link to="/faq">FAQ</Link>
          <Link to="/about">About</Link>
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
            Source code
          </a>
        </nav>
      </footer>
    </div>
  )
}
