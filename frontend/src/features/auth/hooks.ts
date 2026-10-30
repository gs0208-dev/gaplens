import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { fetchMe, login, logout, register, type Credentials } from './api'
import { AccountCreatedError } from './errors'
import { refreshSession } from './refresh'
import type { TokenResponse, User } from './schemas'
import { useAuthStore } from './store'

/** Asks for a session once, when the app starts. A reload loses the token, the cookie restores it. */
export function useSessionRestore(): void {
  useEffect(() => {
    void refreshSession()
  }, [])
}

export function useLogin() {
  const startSession = useStartSession()
  return useMutation({ mutationFn: login, onSuccess: startSession })
}

export function useRegister() {
  const startSession = useStartSession()
  return useMutation({
    mutationFn: async (credentials: Credentials) => {
      await register(credentials)
      try {
        return await login(credentials)
      } catch (error) {
        throw new AccountCreatedError(error)
      }
    },
    onSuccess: startSession,
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logout,
    // Signed out on this device even if the server could not be reached. Forgetting the cached
    // data matters too, so the next person on this browser never sees it.
    onSettled: () => {
      useAuthStore.getState().clearSession()
      queryClient.clear()
    },
  })
}

/** The signed-in user. It is already in the cache from login or refresh, so no request is made. */
export function useCurrentUser(): User | undefined {
  const status = useAuthStore((state) => state.status)
  const { data } = useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    enabled: status === 'authenticated',
    staleTime: Infinity,
  })
  return data
}

function useStartSession() {
  const queryClient = useQueryClient()
  return (data: TokenResponse) => {
    queryClient.setQueryData(['me'], data.user)
    useAuthStore.getState().setSession(data.access_token)
  }
}
