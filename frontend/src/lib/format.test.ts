import { describe, expect, it } from 'vitest'

import { formatDateTime, formatWait } from './format'

describe('formatWait', () => {
  it.each([
    [null, 'a minute'],
    [5, 'a minute'],
    [59, 'a minute'],
    [60, '1 minute'],
    [61, '2 minutes'],
    [900, '15 minutes'],
    [3540, '59 minutes'],
    [3600, '1 hour'],
    [3601, '2 hours'],
    [7200, '2 hours'],
  ])('says %s seconds as %s', (seconds, expected) => {
    expect(formatWait(seconds)).toBe(expected)
  })
})

describe('formatDateTime', () => {
  it('writes the date in the user locale, with the year and the time', () => {
    const text = formatDateTime('2026-11-01T09:30:00Z')

    expect(text).toContain('2026')
    expect(text).toMatch(/\d{1,2}:\d{2}/)
  })
})
