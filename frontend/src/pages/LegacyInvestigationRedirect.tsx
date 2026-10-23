import { Navigate, useParams } from 'react-router-dom'

/** Links shared before the app moved under /app keep working. */
export function LegacyInvestigationRedirect() {
  const { investigationId = '' } = useParams()
  return <Navigate to={`/app/investigations/${investigationId}`} replace />
}
