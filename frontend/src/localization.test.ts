import { describe, expect, it } from 'vitest'
import { formatDateTime, parseApiDateTime } from './localization'

describe('API date localization', () => {
  it('treats timezone-less backend datetimes as UTC before local formatting', () => {
    const value = '2026-09-06T16:30:00.000000'

    expect(parseApiDateTime(value).toISOString()).toBe('2026-09-06T16:30:00.000Z')
    expect(formatDateTime(value)).toBe(formatDateTime(`${value}Z`))
  })
})
