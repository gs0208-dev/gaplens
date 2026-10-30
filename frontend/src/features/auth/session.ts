import { setSessionPort } from '@/lib/api'

import { refreshSession } from './refresh'
import { useAuthStore } from './store'

/** Tells the API client where the access token is and how to renew it. Call once at start-up. */
export function connectSession(): void {
  setSessionPort({
    getAccessToken: () => useAuthStore.getState().accessToken,
    refresh: refreshSession,
  })
}
