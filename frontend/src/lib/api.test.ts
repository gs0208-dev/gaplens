import { beforeEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'

import { problem, stubFetch } from '@/test/fetch'

import { ApiError, apiRequest, setSessionPort, type SessionPort } from './api'

function sessionPort(token: string | null, refresh: SessionPort['refresh'] = async () => false) {
  let current = token
  const port = {
    getAccessToken: vi.fn(() => current),
    refresh: vi.fn(async () => {
      const refreshed = await refresh()
      if (refreshed) current = 'refreshed-token'
      return refreshed
    }),
  }
  setSessionPort(port)
  return port
}

describe('apiRequest', () => {
  beforeEach(() => {
    sessionPort(null)
  })

  it('sends the access token as a bearer header', async () => {
    sessionPort('token-1')
    const fake = stubFetch(() => ({ body: { ok: true } }))

    await apiRequest('/auth/me')

    expect(fake.requests[0]?.url).toBe('/api/v1/auth/me')
    expect(fake.requests[0]?.headers.get('Authorization')).toBe('Bearer token-1')
  })

  it('sends no Authorization header when there is no token', async () => {
    const fake = stubFetch(() => ({ body: {} }))

    await apiRequest('/auth/me')

    expect(fake.requests[0]?.headers.has('Authorization')).toBe(false)
  })

  it('never sends the token when auth is turned off', async () => {
    sessionPort('token-1')
    const fake = stubFetch(() => ({ body: {} }))

    await apiRequest('/auth/login', { method: 'POST', body: {}, auth: false })

    expect(fake.requests[0]?.headers.has('Authorization')).toBe(false)
  })

  it('sends a JSON body with the right content type', async () => {
    const fake = stubFetch(() => ({ body: {} }))

    await apiRequest('/auth/login', { method: 'POST', body: { email: 'a@b.co' }, auth: false })

    expect(fake.requests[0]?.method).toBe('POST')
    expect(fake.requests[0]?.headers.get('Content-Type')).toBe('application/json')
    expect(fake.requests[0]?.body).toEqual({ email: 'a@b.co' })
  })

  it('returns the body checked against the schema', async () => {
    stubFetch(() => ({ body: { name: 'Ana' } }))

    const result = await apiRequest('/x', { schema: z.object({ name: z.string() }) })

    expect(result).toEqual({ name: 'Ana' })
  })

  it('rejects a body that does not match the schema', async () => {
    stubFetch(() => ({ body: { name: 5 } }))

    const failure = apiRequest('/x', { schema: z.object({ name: z.string() }) })

    await expect(failure).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('returns nothing for a 204', async () => {
    stubFetch(() => ({ status: 204 }))

    await expect(apiRequest('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
  })

  it('turns a problem response into an ApiError', async () => {
    stubFetch(() =>
      problem(422, 'validation_error', 'Some fields are missing or invalid.', {
        errors: [{ field: 'password', message: 'String should have at least 12 characters' }],
      }),
    )

    const failure = apiRequest('/auth/register', { method: 'POST', body: {}, auth: false })

    await expect(failure).rejects.toBeInstanceOf(ApiError)
    await expect(failure).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      detail: 'Some fields are missing or invalid.',
      requestId: 'req-12345678',
      fieldErrors: [{ field: 'password', message: 'String should have at least 12 characters' }],
    })
  })

  it('reads Retry-After in seconds', async () => {
    stubFetch(() => ({
      ...problem(429, 'rate_limited', 'Too many attempts.'),
      headers: { 'Retry-After': '60' },
    }))

    const failure = apiRequest('/auth/login', { method: 'POST', body: {}, auth: false })

    await expect(failure).rejects.toMatchObject({ code: 'rate_limited', retryAfterSeconds: 60 })
  })

  it('does not trust an error body that is not JSON', async () => {
    const fake = stubFetch(() => ({ status: 502 }))
    fake.mock.mockImplementation(
      async () => new Response('<html>Bad gateway</html>', { status: 502 }),
    )

    const failure = apiRequest('/auth/me')

    await expect(failure).rejects.toMatchObject({
      status: 502,
      code: 'unexpected_response',
      detail: 'The server returned an unexpected response.',
    })
  })

  it('reports a dropped connection as a network error', async () => {
    stubFetch(() => ({ networkError: true }))

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })
})

describe('apiRequest after an expired access token', () => {
  it('refreshes once and retries once with the new token', async () => {
    const port = sessionPort('old-token', async () => true)
    const fake = stubFetch((request) =>
      request.headers.get('Authorization') === 'Bearer refreshed-token'
        ? { body: { ok: true } }
        : problem(401, 'invalid_access_token', 'The access token is missing, invalid or expired.'),
    )

    const result = await apiRequest('/auth/me', { schema: z.object({ ok: z.boolean() }) })

    expect(result).toEqual({ ok: true })
    expect(port.refresh).toHaveBeenCalledTimes(1)
    expect(fake.requests.map((r) => r.headers.get('Authorization'))).toEqual([
      'Bearer old-token',
      'Bearer refreshed-token',
    ])
  })

  it('gives up with the original error when the refresh fails', async () => {
    const port = sessionPort('old-token', async () => false)
    const fake = stubFetch(() => problem(401, 'invalid_access_token', 'Expired.'))

    const failure = apiRequest('/auth/me')

    await expect(failure).rejects.toMatchObject({ status: 401, code: 'invalid_access_token' })
    expect(port.refresh).toHaveBeenCalledTimes(1)
    expect(fake.requests).toHaveLength(1)
  })

  it('does not loop when the retry is rejected as well', async () => {
    const port = sessionPort('old-token', async () => true)
    const fake = stubFetch(() => problem(401, 'invalid_access_token', 'Expired.'))

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({ status: 401 })

    expect(port.refresh).toHaveBeenCalledTimes(1)
    expect(fake.requests).toHaveLength(2)
  })

  it('does not try to refresh for other 401 errors', async () => {
    const port = sessionPort('token-1', async () => true)
    stubFetch(() => problem(401, 'invalid_credentials', 'The email or password is incorrect.'))

    await expect(
      apiRequest('/auth/login', { method: 'POST', body: {}, auth: false }),
    ).rejects.toMatchObject({ code: 'invalid_credentials' })

    expect(port.refresh).not.toHaveBeenCalled()
  })

  it('does not try to refresh when auth is turned off', async () => {
    const port = sessionPort('token-1', async () => true)
    stubFetch(() => problem(401, 'invalid_access_token', 'Expired.'))

    await expect(apiRequest('/x', { auth: false })).rejects.toMatchObject({ status: 401 })

    expect(port.refresh).not.toHaveBeenCalled()
  })
})
