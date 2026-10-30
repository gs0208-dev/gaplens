import { create } from 'zustand'

// 'unknown' lasts only until the first refresh on page load has answered.
export type AuthStatus = 'unknown' | 'authenticated' | 'anonymous'

interface AuthState {
  status: AuthStatus
  /**
   * The access token lives here, in memory, and nowhere else: not in localStorage, not in
   * sessionStorage, not in a cookie scripts can read. A reload loses it on purpose, and the
   * httpOnly refresh cookie gets a new one (docs/security.md).
   */
  accessToken: string | null
  setSession: (accessToken: string) => void
  clearSession: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: 'unknown',
  accessToken: null,
  setSession: (accessToken) => set({ status: 'authenticated', accessToken }),
  clearSession: () => set({ status: 'anonymous', accessToken: null }),
}))
