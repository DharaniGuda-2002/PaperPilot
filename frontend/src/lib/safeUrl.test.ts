import { describe, expect, it } from 'vitest'

import { safeExternalUrl } from './safeUrl'

describe('safeExternalUrl', () => {
  it.each([
    ['https://arxiv.org/pdf/2005.00625', 'https://arxiv.org/pdf/2005.00625'],
    ['http://example.org/a', 'http://example.org/a'],
    ['javascript:alert(1)', null],
    [' JavaScript:alert(1)', null],
    ['data:text/html,<script>', null],
    ['not a url', null],
    [null, null],
  ])('%s -> %s', (input, expected) => {
    expect(safeExternalUrl(input)).toBe(expected)
  })
})
