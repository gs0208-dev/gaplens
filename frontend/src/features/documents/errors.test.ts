import { describe, expect, it } from 'vitest'

import { ApiError } from '@/lib/api'

import { loadError, uploadError } from './errors'

function apiError(code: string, extra: { retryAfterSeconds?: number; status?: number } = {}) {
  return new ApiError({
    status: extra.status ?? 422,
    code,
    detail: 'Server text that must never be shown.',
    requestId: 'req-12345678',
    fieldErrors: [],
    retryAfterSeconds: extra.retryAfterSeconds ?? null,
  })
}

describe('uploadError', () => {
  it.each([
    ['file_too_large', 'This file is larger than 5 MB.'],
    ['unsupported_file_type', 'Upload a PDF, a plain text file or a Markdown file.'],
    ['encrypted_pdf', 'This PDF is password protected. Remove the protection and upload it again.'],
    ['pdf_unreadable', 'This PDF is damaged or uses a format that cannot be read.'],
    ['too_many_pages', 'This document has more than 100 pages.'],
    ['text_too_long', 'This document has more than 300,000 characters of text.'],
    [
      'no_extractable_text',
      'No text could be read from this file. Scanned documents are not supported.',
    ],
    [
      'duplicate_document',
      'You have already uploaded this file. Delete the earlier one to upload it again.',
    ],
    ['network_error', 'Could not reach the server. Check your connection and try again.'],
    ['validation_error', 'The title can be at most 200 characters.'],
  ])('turns %s into a plain sentence', (code, expected) => {
    expect(uploadError(apiError(code)).message).toBe(expected)
  })

  it('says how long to wait when rate limited', () => {
    const shown = uploadError(apiError('rate_limited', { retryAfterSeconds: 300, status: 429 }))

    expect(shown.message).toBe('You have uploaded too many documents. Try again in 5 minutes.')
  })

  it('keeps the request id and never shows the server text', () => {
    const shown = uploadError(apiError('something_new', { status: 500 }))

    expect(shown).toEqual({ message: 'The upload failed. Try again.', requestId: 'req-12345678' })
  })

  it('handles an error that did not come from the API', () => {
    expect(uploadError(new Error('boom'))).toEqual({
      message: 'The upload failed. Try again.',
      requestId: null,
    })
  })
})

describe('loadError', () => {
  it('names a network failure', () => {
    expect(loadError(apiError('network_error', { status: 0 })).message).toContain('Could not reach')
  })

  it('keeps the request id for any other failure', () => {
    expect(loadError(apiError('internal_error', { status: 500 }))).toEqual({
      message: 'The documents could not be loaded. Try again.',
      requestId: 'req-12345678',
    })
  })
})
