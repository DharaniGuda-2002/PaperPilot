import { ApiError } from '../api/client'

export function LoadingState({ label }: { label: string }) {
  return (
    <p className="muted" role="status">
      {label}
    </p>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : 'Something went wrong.'
  return (
    <p className="notice notice--error" role="alert">
      {message}
    </p>
  )
}
