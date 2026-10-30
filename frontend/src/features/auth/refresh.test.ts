import { beforeEach, describe, expect, it, vi } from 'vitest'

import { queryClient } from '@/lib/query-client'
import { problem, stubFetch, tokenResponse, USER } from '@/test/fetch'

import { refreshSession } from './refresh'
import { useAuthStore } from './store'

const REFRESH_PATH = '/api/v1/auth/refresh'

beforeEach(() => {
  useAuthStore.setState({ status: 'unknown', accessToken: null })
  queryClient.clear()
})

describe('refreshSession', () => {
  it('signs in with the new access token and remembers the user', async () => {
    const fake = stubFetch(() => tokenResponse('fresh-token'))

    const refreshed = await refreshSession()

    expect(refreshed).toBe(true)
    expect(useAuthStore.getState()).toMatchObject({
      status: 'authenticated',
      accessToken: 'fresh-token',
    })
    expect(queryClient.getQueryData(['me'])).toEqual(USER)
    expect(fake.to(REFRESH_PATH)[0]?.method).toBe('POST')
  })

  it('does not send an Authorization header, because the cookie is the credential', async () => {
    useAuthStore.setState({ status: 'authenticated', accessToken: 'stale-token' })
    const fake = stubFetch(() => tokenResponse())

    await refreshSession()

    expect(fake.requests[0]?.headers.has('Authorization')).toBe(false)
  })

  it('signs out quietly when there is no valid session', async () => {
    useAuthStore.setState({ status: 'authenticated', accessToken: 'stale-token' })
    stubFetch(() => problem(401, 'invalid_refresh_token', 'Your session is no longer valid.'))

    const refreshed = await refreshSession()

    expect(refreshed).toBe(false)
    expect(useAuthStore.getState()).toMatchObject({ status: 'anonymous', accessToken: null })
    expect(queryClient.getQueryData(['me'])).toBeUndefined()
  })

  it('treats a network failure as signed out', async () => {
    stubFetch(() => ({ networkError: true }))

    expect(await refreshSession()).toBe(false)
    expect(useAuthStore.getState().status).toBe('anonymous')
  })

  it('sends one request when several callers ask at the same time', async () => {
    const fake = stubFetch(() => tokenResponse())

    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()])

    expect(results).toEqual([true, true, true])
    expect(fake.to(REFRESH_PATH)).toHaveLength(1)
  })

  it('sends a new request for a later call', async () => {
    const fake = stubFetch(() => tokenResponse())

    await refreshSession()
    await refreshSession()

    expect(fake.to(REFRESH_PATH)).toHaveLength(2)
  })

  it('takes a lock shared by every tab of the browser while it refreshes', async () => {
    const locks = {
      request: vi.fn(async (_name: string, callback: () => Promise<boolean>) => callback()),
    }
    Object.defineProperty(navigator, 'locks', { configurable: true, value: locks })
    stubFetch(() => tokenResponse())

    try {
      await refreshSession()
    } finally {
      Reflect.deleteProperty(navigator, 'locks')
    }

    expect(locks.request).toHaveBeenCalledTimes(1)
    expect(locks.request.mock.calls[0]?.[0]).toBe('gaplens-refresh')
  })
})

describe('where the access token is kept', () => {
  it('never writes the token to browser storage or cookies', async () => {
    stubFetch(() => tokenResponse('secret-access-token'))

    await refreshSession()

    expect(useAuthStore.getState().accessToken).toBe('secret-access-token')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(document.cookie).toBe('')
  })
})
