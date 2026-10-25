import { Search } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

/** Top-bar search. Submitting opens the paper search page with the query filled in. */
export function GlobalSearch() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const id = useId()

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return
    navigate(`/app/search?${new URLSearchParams({ q: trimmed })}`)
  }

  return (
    <form className="topbar__search" role="search" onSubmit={onSubmit}>
      <label htmlFor={id} className="visually-hidden">
        Quick search
      </label>
      <Search aria-hidden="true" size={16} />
      <input
        id={id}
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search papers, topics, or ask a question…"
      />
    </form>
  )
}
