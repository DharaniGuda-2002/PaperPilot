import { ArrowRight } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { QUESTION_MAX_LENGTH } from '../../api/types'
import { ErrorState } from '../../components/QueryState'
import { useCreateInvestigation } from './hooks'
import { EXAMPLE_QUESTIONS } from './status'
import { validateQuestion } from './validation'

/** One-line question input with a submit arrow and example prompts. */
export function QuickStartForm({ label, placeholder }: { label: string; placeholder: string }) {
  const [question, setQuestion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const create = useCreateInvestigation()
  const navigate = useNavigate()
  const inputId = useId()
  const errorId = useId()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const problem = validateQuestion(question)
    setError(problem)
    if (problem) return
    create.mutate(question.trim(), {
      onSuccess: (created) => navigate(`/app/investigations/${created.id}`),
    })
  }

  return (
    <form className="quick-start" onSubmit={handleSubmit} noValidate>
      <label htmlFor={inputId} className="visually-hidden">
        {label}
      </label>
      <div className="quick-start__field">
        <input
          id={inputId}
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={placeholder}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          maxLength={QUESTION_MAX_LENGTH + 50}
        />
        <button
          type="submit"
          className="icon-button icon-button--primary"
          disabled={create.isPending}
          aria-label={create.isPending ? 'Starting investigation' : 'Start investigation'}
        >
          <ArrowRight aria-hidden="true" size={18} />
        </button>
      </div>
      {error && (
        <p id={errorId} className="field-error">
          {error}
        </p>
      )}
      {create.isError && <ErrorState error={create.error} />}
      <div className="examples">
        <span className="examples__label">Try an example:</span>
        {EXAMPLE_QUESTIONS.map((example) => (
          <button
            key={example.label}
            type="button"
            className="chip"
            onClick={() => {
              setQuestion(example.question)
              setError(null)
            }}
          >
            {example.label}
          </button>
        ))}
      </div>
    </form>
  )
}
