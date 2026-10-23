import { useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { QUESTION_MAX_LENGTH, QUESTION_MIN_LENGTH } from '../../api/types'
import { ErrorState } from '../../components/QueryState'
import { useCreateInvestigation } from './hooks'

export function QuestionForm() {
  const [question, setQuestion] = useState('')
  const [touched, setTouched] = useState(false)
  const create = useCreateInvestigation()
  const navigate = useNavigate()
  const inputId = useId()
  const hintId = useId()
  const errorId = useId()

  const trimmedLength = question.trim().length
  const validationError =
    trimmedLength < QUESTION_MIN_LENGTH
      ? `Enter at least ${QUESTION_MIN_LENGTH} characters.`
      : trimmedLength > QUESTION_MAX_LENGTH
        ? `Keep the question under ${QUESTION_MAX_LENGTH} characters.`
        : null
  const showError = touched && validationError !== null

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    if (validationError) return
    create.mutate(question.trim(), {
      onSuccess: (created) => navigate(`/investigations/${created.id}`),
    })
  }

  return (
    <form className="question-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor={inputId}>Research question</label>
      <textarea
        id={inputId}
        name="question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onBlur={() => setTouched(true)}
        placeholder="e.g. Do graph neural networks outperform gradient boosting for fraud detection on imbalanced data?"
        aria-describedby={showError ? `${hintId} ${errorId}` : hintId}
        aria-invalid={showError}
        maxLength={QUESTION_MAX_LENGTH + 50}
      />
      {showError && (
        <p id={errorId} className="field-error">
          {validationError}
        </p>
      )}
      <div className="question-form__footer">
        <p id={hintId} className="hint">
          {trimmedLength}/{QUESTION_MAX_LENGTH} characters. Ask a specific, technical question.
        </p>
        <button type="submit" className="button button--primary" disabled={create.isPending}>
          {create.isPending ? 'Starting…' : 'Start investigation'}
        </button>
      </div>
      {create.isError && <ErrorState error={create.error} />}
    </form>
  )
}
