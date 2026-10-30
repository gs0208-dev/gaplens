import { apiRequest } from '@/lib/api'

import { tokenResponseSchema, userResponseSchema, type User } from './schemas'

export interface Credentials {
  email: string
  password: string
}

// Login, register and logout do not carry the access token: login and register have none yet,
// and logout is authorised by the refresh cookie.

export function login(credentials: Credentials) {
  return apiRequest('/auth/login', {
    method: 'POST',
    body: credentials,
    auth: false,
    schema: tokenResponseSchema,
  })
}

export function register(credentials: Credentials) {
  return apiRequest('/auth/register', {
    method: 'POST',
    body: credentials,
    auth: false,
    schema: userResponseSchema,
  })
}

export function logout() {
  return apiRequest('/auth/logout', { method: 'POST', auth: false })
}

export async function fetchMe(): Promise<User> {
  const body = await apiRequest('/auth/me', { schema: userResponseSchema })
  return body.user
}
