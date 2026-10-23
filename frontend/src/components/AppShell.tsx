import { Link, NavLink, Outlet } from 'react-router-dom'

export function AppShell() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="site-header">
        <div className="site-header__inner">
          <Link to="/" className="brand">
            PaperPilot
          </Link>
          <nav aria-label="Main" className="site-nav">
            <NavLink to="/" end>
              Dashboard
            </NavLink>
          </nav>
        </div>
      </header>
      <main id="main" className="page" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}
