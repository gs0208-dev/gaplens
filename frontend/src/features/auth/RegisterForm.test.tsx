import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { problem, stubApi, tokenResponse, USER } from '@/test/fetch'
import { renderApp, resetClientState } from '@/test/render'

const REFRESH = 'POST /api/v1/auth/refresh'
const REGISTER = 'POST /api/v1/auth/register'
const LOGIN = 'POST /api/v1/auth/login'
const noSession = () => problem(401, 'invalid_refresh_token', 'Your session is no longer valid.')
const registered = () => ({ status: 201, body: { user: USER } })

beforeEach(resetClientState)

async function openRegisterPage(extraRoutes: Parameters<typeof stubApi>[0] = {}) {
  const fake = stubApi({ [REFRESH]: noSession, ...extraRoutes })
  const page = renderApp('/register')
  await screen.findByRole('heading', { name: 'Create an account' })
  return { fake, ...page }
}

async function fillAndSubmit(
  user: Awaited<ReturnType<typeof openRegisterPage>>['user'],
  password: string,
) {
  await user.type(screen.getByLabelText('Email'), 'ana@example.com')
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Create account' }))
}

describe('the register form', () => {
  it('states the password rule and uses the new-password hint', async () => {
    await openRegisterPage()

    const password = screen.getByLabelText('Password')
    expect(password).toHaveAttribute('autocomplete', 'new-password')
    expect(password).toHaveAccessibleDescription('12 to 128 characters.')
  })

  it('rejects a password under 12 characters without calling the server', async () => {
    const { fake, user } = await openRegisterPage()

    await fillAndSubmit(user, 'a'.repeat(11))

    expect(await screen.findByText('Use at least 12 characters.')).toBeInTheDocument()
    expect(fake.to('/api/v1/auth/register')).toHaveLength(0)
  })

  it('rejects a password over 128 characters', async () => {
    const { fake, user } = await openRegisterPage()

    await fillAndSubmit(user, 'a'.repeat(129))

    expect(await screen.findByText('Use at most 128 characters.')).toBeInTheDocument()
    expect(fake.to('/api/v1/auth/register')).toHaveLength(0)
  })

  it('accepts exactly 12 characters', async () => {
    const { fake, user } = await openRegisterPage({
      [REGISTER]: registered,
      [LOGIN]: () => tokenResponse(),
    })

    await fillAndSubmit(user, 'a'.repeat(12))

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    expect(fake.to('/api/v1/auth/register')).toHaveLength(1)
  })

  it('registers, then signs the new user in with the same details', async () => {
    const { fake, user } = await openRegisterPage({
      [REGISTER]: registered,
      [LOGIN]: () => tokenResponse(),
    })

    await fillAndSubmit(user, 'correct horse battery')

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    const body = { email: 'ana@example.com', password: 'correct horse battery' }
    expect(fake.to('/api/v1/auth/register')[0]?.body).toEqual(body)
    expect(fake.to('/api/v1/auth/login')[0]?.body).toEqual(body)
  })

  it('shows a duplicate email under the email field, not as a general error', async () => {
    const { user } = await openRegisterPage({
      [REGISTER]: () =>
        problem(409, 'email_already_registered', 'An account with this email already exists.'),
    })

    await fillAndSubmit(user, 'correct horse battery')

    const email = screen.getByLabelText('Email')
    expect(
      await screen.findByText('An account with this email already exists.'),
    ).toBeInTheDocument()
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveAccessibleDescription('An account with this email already exists.')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('tells the user when the account was created but signing in failed', async () => {
    const { user } = await openRegisterPage({
      [REGISTER]: registered,
      [LOGIN]: () => problem(429, 'rate_limited', 'Too many attempts.'),
    })

    await fillAndSubmit(user, 'correct horse battery')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your account was created, but signing in failed. Sign in with your new details.',
    )
  })

  it('links to the sign-in page', async () => {
    await openRegisterPage()

    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
  })
})
