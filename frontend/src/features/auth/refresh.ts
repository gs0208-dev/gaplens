import { ApiError, apiRequest } from '@/lib/api'
import { queryClient } from '@/lib/query-client'

import { tokenResponseSchema } from './schemas'
import { useAuthStore } from './store'

const LOCK_NAME = 'gaplens-refresh'

let inFlight: Promise<boolean> | null = null

/**
 * Trades the refresh cookie for a new access token. Resolves to false when there is no session.
 *
 * The server rotates the cookie on every refresh and treats a second use of the old one as
 * theft (ADR-022). So two refreshes must never run side by side with the same cookie:
 * - callers in this tab share one request, which also covers React's development mode running
 *   effects twice;
 * - tabs of the same browser take turns through a Web Lock, so the second tab sends the cookie
 *   the first tab just received.
 */
export function refreshSession(): Promise<boolean> {
  inFlight ??= withLockAcrossTabs(refreshOnce).finally(() => {
    inFlight = null
  })
  return inFlight
}

function withLockAcrossTabs<T>(task: () => Promise<T>): Promise<T> {
  // Browsers without the Web Locks API still get the one-request-per-tab protection above.
  const locks: LockManager | undefined =
    typeof navigator === 'undefined' ? undefined : navigator.locks
  return locks === undefined ? task() : locks.request(LOCK_NAME, task)
}

async function refreshOnce(): Promise<boolean> {
  try {
    const body = await apiRequest('/auth/refresh', {
      method: 'POST',
      auth: false,
      schema: tokenResponseSchema,
    })
    // The user goes in the cache first, so the screens that appear when the status changes
    // already find them there.
    queryClient.setQueryData(['me'], body.user)
    useAuthStore.getState().setSession(body.access_token)
    return true
  } catch (error) {
    // No cookie, an expired one, a dropped connection: in every case there is no session to
    // continue. Anything that is not an ApiError is a bug and is left to surface.
    if (!(error instanceof ApiError)) {
      throw error
    }
    queryClient.removeQueries({ queryKey: ['me'] })
    useAuthStore.getState().clearSession()
    return false
  }
}
