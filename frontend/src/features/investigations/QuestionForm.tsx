import { ArrowRight } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { QUESTION_MAX_LENGTH } from '../../api/types'
import { ErrorState } from '../../components/QueryState'
import { useCreateInvestigation } from './hooks'
import { validateQuestion } from './validation'

/** Full research-question form used on the New Investigation page. */
export function QuestionForm() {
  const [question, setQuestion] = useState('')
  const [touched, setTouched] = useState(false)
  const create = useCreateInvestigation()
  const navigate = useNavigate()
  const inputId = useId()
  const hintId = useId()
  const errorId = useId()

  const validationError = validateQuestion(question)
  const showError = touched && validationError !== null

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    if (validationError) return
    create.mutate(question.trim(), {
      onSuccess: (created) => navigate(`/app/investigations/${created.id}`),
    })
  }

  return (
    <form className="question-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor={inputId}>Research question</label>
      <div className="question-form__box">
        <textarea
          id={inputId}
          name="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onBlur={() => setTouched(true)}
          placeholder="e.g. Do graph neural networks outperform traditional machine learning for financial fraud detection on highly imbalanced datasets?"
          aria-describedby={showError ? `${hintId} ${errorId}` : hintId}
          aria-invalid={showError}
          maxLength={QUESTION_MAX_LENGTH + 50}
        />
        <span id={hintId} className="question-form__count">
          {question.trim().length}/{QUESTION_MAX_LENGTH}
        </span>
      </div>
      {showError && (
        <p id={errorId} className="field-error">
          {validationError}
        </p>
      )}
      <p className="hint">Ask one specific, technical question. Narrow questions give clearer evidence.</p>
      <div className="source-chips" aria-label="Sources and limits">
        <span className="source-chips__label">Sources and limits</span>
        <span className="chip chip--static">Papers from OpenAlex</span>
        <span className="chip chip--static">Up to 25 papers</span>
        <span className="chip chip--static">Open-access PDFs only</span>
      </div>
      <div className="form-actions">
        <button type="submit" className="button button--primary" disabled={create.isPending}>
          {create.isPending ? 'Starting…' : 'Run investigation'}
          <ArrowRight aria-hidden="true" size={16} />
        </button>
      </div>
      {create.isError && <ErrorState error={create.error} />}
    </form>
  )
}
