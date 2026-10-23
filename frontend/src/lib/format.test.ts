import { describe, expect, it } from 'vitest'

import { formatRelative } from './format'

const NOW = new Date('2026-10-22T12:00:00Z')

describe('formatRelative', () => {
  it.each([
    ['2026-10-22T11:59:40Z', 'just now'],
    ['2026-10-22T11:55:00Z', '5 minutes ago'],
    ['2026-10-22T10:00:00Z', '2 hours ago'],
    ['2026-10-21T12:00:00Z', 'yesterday'],
  ])('%s -> %s', (iso, expected) => {
    expect(formatRelative(iso, NOW)).toBe(expected)
  })
})
