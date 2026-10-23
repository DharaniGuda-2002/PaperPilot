import { Search } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  SEARCH_MAX_PAGE,
  SEARCH_QUERY_MIN_LENGTH,
  type PaperSearchParams,
  type SearchSort,
} from '../api/types'
import { ErrorState, LoadingState } from '../components/QueryState'
import { usePaperSearch } from '../features/papers/hooks'
import { PaperResult } from '../features/papers/PaperResult'
import { formatRelative } from '../lib/format'

const PER_PAGE = 10
const CURRENT_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: CURRENT_YEAR - 1990 + 1 }, (_, i) => CURRENT_YEAR - i)
const SORTS: { value: SearchSort; label: string }[] = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'citations', label: 'Most cited' },
  { value: 'newest', label: 'Newest' },
]
const EXAMPLES = ['graph neural networks fraud detection', 'LLM evaluation benchmarks', 'solar power forecasting']

/** URL query string is the single source of truth, so searches are shareable. */
function readParams(search: URLSearchParams): PaperSearchParams | null {
  const q = search.get('q')?.trim() ?? ''
  if (q.length < SEARCH_QUERY_MIN_LENGTH) return null
  const year = (key: string) => {
    const value = Number(search.get(key))
    return Number.isInteger(value) && value > 0 ? value : undefined
  }
  const sort = search.get('sort')
  return {
    q,
    from_year: year('from_year'),
    to_year: year('to_year'),
    open_access_only: search.get('open_access_only') === 'true' || undefined,
    sort: SORTS.some((s) => s.value === sort) ? (sort as SearchSort) : undefined,
    page: Math.min(Math.max(year('page') ?? 1, 1), SEARCH_MAX_PAGE),
    per_page: PER_PAGE,
  }
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const params = readParams(searchParams)
  const [draft, setDraft] = useState(searchParams.get('q') ?? '')
  const [draftError, setDraftError] = useState<string | null>(null)
  const { data, isPending, isFetching, isError, error } = usePaperSearch(params)
  const inputId = useId()

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
    }
    if (!('page' in changes)) next.delete('page') // filters reset to page 1
    setSearchParams(next)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (draft.trim().length < SEARCH_QUERY_MIN_LENGTH) {
      setDraftError(`Enter at least ${SEARCH_QUERY_MIN_LENGTH} characters.`)
      return
    }
    setDraftError(null)
    update({ q: draft.trim() })
  }

  const totalPages = data
    ? Math.min(Math.ceil(data.total / PER_PAGE), SEARCH_MAX_PAGE)
    : 0

  return (
    <div className="page page--wide">
      <header className="page-header">
        <div>
          <h1 className="page-title">Search papers</h1>
          <p className="page-subtitle">
            Search scholarly works indexed by OpenAlex. Results include open-access availability.
          </p>
        </div>
      </header>

      <form className="search-bar" role="search" onSubmit={handleSubmit} noValidate>
        <label htmlFor={inputId} className="visually-hidden">
          Search papers
        </label>
        <div className="quick-start__field search-bar__field">
          <Search aria-hidden="true" size={18} className="search-bar__icon" />
          <input
            id={inputId}
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="e.g. graph neural networks fraud detection"
            maxLength={200}
            aria-invalid={draftError !== null}
          />
          <button type="submit" className="button button--primary">
            Search
          </button>
        </div>
        {draftError && <p className="field-error">{draftError}</p>}
      </form>

      <div className="search-layout">
        <aside className="card filters" aria-label="Filters">
          <h2 className="card__title">Filters</h2>
          <label className="field">
            <span>From year</span>
            <select
              value={searchParams.get('from_year') ?? ''}
              onChange={(e) => update({ from_year: e.target.value })}
            >
              <option value="">Any</option>
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>To year</span>
            <select
              value={searchParams.get('to_year') ?? ''}
              onChange={(e) => update({ to_year: e.target.value })}
            >
              <option value="">Any</option>
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={searchParams.get('open_access_only') === 'true'}
              onChange={(e) => update({ open_access_only: e.target.checked ? 'true' : null })}
            />
            Open access only
          </label>
          <label className="field">
            <span>Sort by</span>
            <select
              value={searchParams.get('sort') ?? 'relevance'}
              onChange={(e) => update({ sort: e.target.value === 'relevance' ? null : e.target.value })}
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </aside>

        <section className="card results" aria-labelledby="results-heading" aria-busy={isFetching}>
          {params === null ? (
            <div className="results__intro">
              <h2 id="results-heading" className="card__title">
                Find relevant papers
              </h2>
              <p className="page-subtitle">Enter a topic above, or try one of these:</p>
              <div className="examples">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="chip"
                    onClick={() => {
                      setDraft(example)
                      update({ q: example })
                    }}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ) : isPending ? (
            <LoadingState label="Searching OpenAlex… (the first search after idle can be slow)" />
          ) : isError ? (
            <ErrorState error={error} />
          ) : (
            <>
              <div className="card__header">
                <h2 id="results-heading" className="card__title">
                  {data.total.toLocaleString()} papers
                </h2>
                <p className="results__source">
                  From OpenAlex, {data.cached ? 'cached' : 'fetched'}{' '}
                  {formatRelative(data.fetched_at)}
                </p>
              </div>
              {data.results.length === 0 ? (
                <p className="empty">No papers matched. Try broader terms or fewer filters.</p>
              ) : (
                <ol className="paper-results" start={(data.page - 1) * PER_PAGE + 1}>
                  {data.results.map(({ paper }) => (
                    <li key={paper.id}>
                      <PaperResult paper={paper} />
                    </li>
                  ))}
                </ol>
              )}
              {totalPages > 1 && (
                <nav className="pagination" aria-label="Pagination">
                  <span className="pagination__summary">
                    Page {data.page} of {totalPages}
                  </span>
                  <button
                    type="button"
                    className="button button--secondary"
                    disabled={data.page <= 1 || isFetching}
                    onClick={() => update({ page: String(data.page - 1) })}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    className="button button--secondary"
                    disabled={data.page >= totalPages || isFetching}
                    onClick={() => update({ page: String(data.page + 1) })}
                  >
                    Next
                  </button>
                </nav>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
