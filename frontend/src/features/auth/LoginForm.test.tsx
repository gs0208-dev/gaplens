import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { problem, stubApi, tokenResponse } from '@/test/fetch'
import { renderApp, resetClientState } from '@/test/render'

const REFRESH = 'POST /api/v1/auth/refresh'
const LOGIN = 'POST /api/v1/auth/login'
const noSession = () => problem(401, 'invalid_refresh_token', 'Your session is no longer valid.')

beforeEach(resetClientState)

async function openLoginPage(extraRoutes: Parameters<typeof stubApi>[0] = {}) {
  const fake = stubApi({ [REFRESH]: noSession, ...extraRoutes })
  const page = renderApp('/login')
  await screen.findByRole('heading', { name: 'Sign in' })
  return { fake, ...page }
}

describe('the sign-in form', () => {
  it('labels both fields and uses the right autocomplete hints', async () => {
    await openLoginPage()

    expect(screen.getByLabelText('Email')).toHaveAttribute('autocomplete', 'email')
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'current-password')
  })

  it('asks for the missing fields without calling the server', async () => {
    const { fake, user } = await openLoginPage()

    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(fake.to('/api/v1/auth/login')).toHaveLength(0)
  })

  it('links an error to its field so a screen reader announces it', async () => {
    const { user } = await openLoginPage()

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const email = screen.getByLabelText('Email')
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveAccessibleDescription('Enter a valid email address.')
  })

  it('sends the trimmed email and the password, then shows the signed-in page', async () => {
    const { fake, user } = await openLoginPage({ [LOGIN]: () => tokenResponse() })

    await user.type(screen.getByLabelText('Email'), '  ana@example.com  ')
    await user.type(screen.getByLabelText('Password'), 'correct horse battery')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
    expect(fake.to('/api/v1/auth/login')[0]?.body).toEqual({
      email: 'ana@example.com',
      password: 'correct horse battery',
    })
  })

  it('disables the button while the request is running', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const { user } = await openLoginPage({
      [LOGIN]: async () => {
        await gate
        return tokenResponse()
      },
    })

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct horse battery')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
    release()
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  })

  it('shows the server message and request id in an alert after a wrong password', async () => {
    const { user } = await openLoginPage({
      [LOGIN]: () => problem(401, 'invalid_credentials', 'The email or password is incorrect.'),
    })

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong horse battery')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The email or password is incorrect.')
    expect(alert).toHaveTextContent('Request ID: req-12345678')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('says how long to wait when the rate limit is hit', async () => {
    const { user } = await openLoginPage({
      [LOGIN]: () => ({
        ...problem(429, 'rate_limited', 'Too many attempts. Try again later.'),
        headers: { 'Retry-After': '60' },
      }),
    })

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Password'), 'anything')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many attempts. Try again in 1 minute.',
    )
  })

  it('explains a dropped connection', async () => {
    const { user } = await openLoginPage({ [LOGIN]: () => ({ networkError: true }) })

    await user.type(screen.getByLabelText('Email'), 'ana@example.com')
    await user.type(screen.getByLabelText('Password'), 'anything')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not reach the server. Check your connection and try again.',
    )
  })

  it('links to the register page', async () => {
    await openLoginPage()

    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute(
      'href',
      '/register',
    )
  })
})
