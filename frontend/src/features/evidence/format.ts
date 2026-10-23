import type { EvidenceField, EvidenceItem } from '../../api/types'

export const FIELD_LABELS: Record<EvidenceField, string> = {
  metric_result: 'Result',
  method: 'Method',
  baseline: 'Baseline',
  dataset: 'Dataset',
  split: 'Split / protocol',
  limitation: 'Limitation',
  code_availability: 'Code',
}

export const FIELD_ORDER: EvidenceField[] = [
  'metric_result',
  'method',
  'baseline',
  'dataset',
  'split',
  'limitation',
  'code_availability',
]

function text(value: unknown): string {
  return value === null || value === undefined ? '' : String(value)
}

/** One-line summary of an extracted value; the passage remains the source of truth. */
export function describeValue(item: EvidenceItem): string {
  const v = item.value ?? {}
  switch (item.field) {
    case 'metric_result': {
      const unit = v.unit === '%' ? '%' : ''
      const method = v.method_hint ? ` · ${text(v.method_hint)}` : ''
      return `${text(v.metric)} ${text(v.value)}${unit}${method}`
    }
    case 'method':
      return v.role === 'proposed' ? `${text(v.name)} (proposed)` : text(v.name)
    case 'baseline':
    case 'dataset':
      return text(v.name)
    case 'split': {
      const parts = ['k', 'train', 'valid', 'test']
        .filter((key) => v[key] !== undefined)
        .map((key) => (key === 'k' ? `k=${text(v[key])}` : `${key} ${text(v[key])}%`))
      return [text(v.protocol), ...parts].join(' · ')
    }
    case 'limitation':
      return 'Limitation stated'
    case 'code_availability':
      return v.url ? text(v.url) : `Code ${text(v.statement)}`
  }
}
