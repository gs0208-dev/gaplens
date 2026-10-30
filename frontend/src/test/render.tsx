import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { createMemoryRouter } from 'react-router'

import { App } from '@/app/App'
import { AppProviders } from '@/app/providers'
import { routes } from '@/app/routes'
import { useAuthStore } from '@/features/auth/store'
import { queryClient } from '@/lib/query-client'

/** Starts every test signed out, with an empty cache. */
export function resetClientState(): void {
  useAuthStore.setState({ status: 'unknown', accessToken: null })
  queryClient.clear()
}

/**
 * Renders the real app at a path, inside StrictMode like main.tsx. StrictMode runs effects twice
 * in development, which is exactly what the session restore has to survive.
 */
export function renderApp(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  // Every path the router lands on, so a test can see a detour that is gone by the end.
  const visited: string[] = [router.state.location.pathname]
  router.subscribe((state) => visited.push(state.location.pathname))
  const user = userEvent.setup()
  render(
    <StrictMode>
      <AppProviders>
        <App router={router} />
      </AppProviders>
    </StrictMode>,
  )
  return { user, router, visited }
}
