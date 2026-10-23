import type { RouteObject } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { InvestigationPage } from './pages/InvestigationPage'
import { NotFoundPage } from './pages/NotFoundPage'

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'investigations/:investigationId', element: <InvestigationPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
