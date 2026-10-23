import { QUESTION_MAX_LENGTH, QUESTION_MIN_LENGTH } from '../../api/types'

/** Mirrors the API's question rules so users see problems before submitting. */
export function validateQuestion(question: string): string | null {
  const length = question.trim().length
  if (length < QUESTION_MIN_LENGTH) return `Enter at least ${QUESTION_MIN_LENGTH} characters.`
  if (length > QUESTION_MAX_LENGTH) return `Keep the question under ${QUESTION_MAX_LENGTH} characters.`
  return null
}
