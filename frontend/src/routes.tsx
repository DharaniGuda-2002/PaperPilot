import type { RouteObject } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { InvestigationPage } from './pages/InvestigationPage'
import { InvestigationsPage } from './pages/InvestigationsPage'
import { LandingPage } from './pages/LandingPage'
import { LegacyInvestigationRedirect } from './pages/LegacyInvestigationRedirect'
import { NewInvestigationPage } from './pages/NewInvestigationPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PaperPage } from './pages/PaperPage'
import { SearchPage } from './pages/SearchPage'

export const routes: RouteObject[] = [
  { path: '/', element: <LandingPage /> },
  { path: '/investigations/:investigationId', element: <LegacyInvestigationRedirect /> },
  {
    path: '/app',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'investigations', element: <InvestigationsPage /> },
      { path: 'investigations/new', element: <NewInvestigationPage /> },
      { path: 'investigations/:investigationId', element: <InvestigationPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'papers/:paperId', element: <PaperPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  { path: '*', element: <AppShell />, children: [{ path: '*', element: <NotFoundPage /> }] },
]
