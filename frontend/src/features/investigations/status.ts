import type { InvestigationStatus } from '../../api/types'

export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'error'

export const STATUS_DISPLAY: Record<InvestigationStatus, { label: string; tone: StatusTone }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  running: { label: 'In progress', tone: 'info' },
  completed: { label: 'Completed', tone: 'success' },
  partially_completed: { label: 'Partially completed', tone: 'warning' },
  failed: { label: 'Failed', tone: 'error' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

/** Example prompts offered to the user. They are suggestions, not research results. */
export const EXAMPLE_QUESTIONS = [
  {
    label: 'GNNs for fraud detection',
    question:
      'Do graph neural networks outperform traditional machine learning for financial fraud detection on highly imbalanced datasets?',
  },
  {
    label: 'LLM evaluation methods',
    question:
      'Which evaluation methods for large language models best predict performance on real downstream tasks?',
  },
  {
    label: 'Climate change mitigation',
    question:
      'Which machine learning approaches improve short-term solar and wind power forecasting accuracy?',
  },
]
