import { describe, expect, it } from 'vitest'

import { ApiError } from '@/lib/api'

import { chatError } from './errors'

function apiError(code: string, retryAfterSeconds: number | null = null) {
  return new ApiError({
    status: 503,
    code,
    detail: 'Server text that must never be shown.',
    requestId: 'req-12345678',
    fieldErrors: [],
    retryAfterSeconds,
  })
}

describe('chatError', () => {
  it.each([
    ['document_not_ready', 'This document is still being processed. Try again when it is ready.'],
    ['document_not_found', 'This document no longer exists.'],
    ['llm_unavailable', 'Answers are not available right now. Try again later.'],
    ['llm_timeout', 'The answer took too long. Try again.'],
    ['llm_invalid_output', 'An answer could not be produced. Try again.'],
    ['validation_error', 'A question can be 1 to 1,000 characters long.'],
  ])('turns %s into a plain sentence', (code, expected) => {
    expect(chatError(apiError(code)).message).toBe(expected)
  })

  it('says how long to wait when rate limited', () => {
    expect(chatError(apiError('rate_limited', 1800)).message).toBe(
      'You have asked too many questions. Try again in 30 minutes.',
    )
  })

  it('asks for a new conversation when the saved one is gone', () => {
    const view = chatError(apiError('thread_not_found'))

    expect(view.startNewThread).toBe(true)
    expect(view.message).toContain('start a new one')
  })

  it('keeps the request id and does not start a new thread for other errors', () => {
    const view = chatError(apiError('llm_timeout'))

    expect(view.requestId).toBe('req-12345678')
    expect(view.startNewThread).toBe(false)
  })

  it('never shows text the server wrote', () => {
    expect(chatError(apiError('brand_new_code')).message).toBe(
      'The question could not be answered. Try again.',
    )
    expect(chatError(new Error('boom')).message).toBe('The question could not be sent. Try again.')
  })
})
