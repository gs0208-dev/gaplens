import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAuthStore } from '@/features/auth/store'
import { problem, stubApi, tokenResponse, USER } from '@/test/fetch'
import { renderApp, resetClientState } from '@/test/render'

const REFRESH = 'POST /api/v1/auth/refresh'
const LOGOUT = 'POST /api/v1/auth/logout'
const noSession = () => problem(401, 'invalid_refresh_token', 'Your session is no longer valid.')

beforeEach(resetClientState)

describe('restoring the session on load', () => {
  it('shows the signed-in page when the refresh cookie is still good', async () => {
    const fake = stubApi({ [REFRESH]: () => tokenResponse() })

    renderApp('/documents')

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    expect(screen.getByText(USER.email)).toBeInTheDocument()
    // StrictMode runs the start-up effect twice. One request must still be enough.
    expect(fake.to('/api/v1/auth/refresh')).toHaveLength(1)
  })

  it('shows a loading skeleton, not the login page, while it waits', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    stubApi({
      [REFRESH]: async () => {
        await gate
        return tokenResponse()
      },
    })

    renderApp('/documents')

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
    release()
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  })

  it('does not bounce through the login page while it waits, so a deep link survives a reload', async () => {
    stubApi({ [REFRESH]: () => tokenResponse() })

    const { visited } = renderApp('/documents')

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    expect(visited).not.toContain('/login')
  })

  it('goes to the login page without any error when there is no session', async () => {
    stubApi({ [REFRESH]: noSession })

    renderApp('/documents')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('routes', () => {
  it('sends a signed-in user from the login page to the documents page', async () => {
    stubApi({ [REFRESH]: () => tokenResponse() })

    renderApp('/login')

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  })

  it('sends a signed-in user from the register page to the documents page', async () => {
    stubApi({ [REFRESH]: () => tokenResponse() })

    renderApp('/register')

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  })

  it('shows a not-found page for an unknown path', async () => {
    stubApi({ [REFRESH]: noSession })

    renderApp('/no-such-page')

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('opens the login page at the root when signed out', async () => {
    stubApi({ [REFRESH]: noSession })

    renderApp('/')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})

describe('signing out', () => {
  it('ends the session, forgets the token and returns to the login page', async () => {
    const fake = stubApi({
      [REFRESH]: () => tokenResponse('token-to-forget'),
      [LOGOUT]: () => ({ status: 204 }),
    })
    const { user } = renderApp('/documents')

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(fake.to('/api/v1/auth/logout')).toHaveLength(1)
    expect(fake.to('/api/v1/auth/logout')[0]?.headers.get('Authorization')).toBeNull()
    expect(useAuthStore.getState()).toMatchObject({ status: 'anonymous', accessToken: null })
  })

  it('still signs out on this device when the server cannot be reached', async () => {
    stubApi({
      [REFRESH]: () => tokenResponse(),
      [LOGOUT]: () => ({ networkError: true }),
    })
    const { user } = renderApp('/documents')

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(useAuthStore.getState().accessToken).toBeNull())
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})
