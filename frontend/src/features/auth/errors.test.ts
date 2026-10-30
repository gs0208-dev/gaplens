import { describe, expect, it } from 'vitest'

import { ApiError } from '@/lib/api'

import { describeError } from './errors'

function apiError(overrides: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({
    status: 400,
    code: 'bad_request',
    detail: 'The request could not be processed.',
    requestId: 'req-12345678',
    fieldErrors: [],
    retryAfterSeconds: null,
    ...overrides,
  })
}

describe('describeError', () => {
  it('shows the server message for a wrong password, with the request id', () => {
    const described = describeError(
      apiError({
        status: 401,
        code: 'invalid_credentials',
        detail: 'The email or password is incorrect.',
      }),
    )

    expect(described).toEqual({
      message: 'The email or password is incorrect.',
      requestId: 'req-12345678',
      fieldErrors: {},
    })
  })

  it('says how long to wait after a rate limit', () => {
    expect(
      describeError(apiError({ status: 429, code: 'rate_limited', retryAfterSeconds: 60 })).message,
    ).toBe('Too many attempts. Try again in 1 minute.')
    expect(
      describeError(apiError({ status: 429, code: 'rate_limited', retryAfterSeconds: 45 })).message,
    ).toBe('Too many attempts. Try again in 45 seconds.')
    expect(
      describeError(apiError({ status: 429, code: 'rate_limited', retryAfterSeconds: 900 }))
        .message,
    ).toBe('Too many attempts. Try again in 15 minutes.')
  })

  it('does not invent a wait time when the server gave none', () => {
    expect(describeError(apiError({ status: 429, code: 'rate_limited' })).message).toBe(
      'Too many attempts. Try again in a few minutes.',
    )
  })

  it('puts a duplicate email on the email field instead of the summary', () => {
    const described = describeError(
      apiError({
        status: 409,
        code: 'email_already_registered',
        detail: 'An account with this email already exists.',
      }),
    )

    expect(described.message).toBeNull()
    expect(described.fieldErrors).toEqual({ email: 'An account with this email already exists.' })
  })

  it('maps server validation errors to their fields', () => {
    const described = describeError(
      apiError({
        status: 422,
        code: 'validation_error',
        fieldErrors: [{ field: 'password', message: 'String should have at least 12 characters' }],
      }),
    )

    expect(described.message).toBeNull()
    expect(described.fieldErrors.password).toBe('String should have at least 12 characters')
  })

  it('keeps a summary for validation errors on fields the form does not show', () => {
    const described = describeError(
      apiError({
        status: 422,
        code: 'validation_error',
        detail: 'Some fields are missing or invalid.',
        fieldErrors: [{ field: 'role', message: 'Extra inputs are not permitted' }],
      }),
    )

    expect(described.message).toBe('Some fields are missing or invalid.')
  })

  it('explains a dropped connection and has no request id to show', () => {
    expect(
      describeError(apiError({ status: 0, code: 'network_error', detail: 'x', requestId: null })),
    ).toEqual({
      message: 'Could not reach the server. Check your connection and try again.',
      requestId: null,
      fieldErrors: {},
    })
  })

  it('gives a generic message for an error it does not know', () => {
    expect(describeError(new Error('boom'))).toEqual({
      message: 'Something went wrong. Try again.',
      requestId: null,
      fieldErrors: {},
    })
  })
})
