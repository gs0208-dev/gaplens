import { vi, type Mock } from 'vitest'

export interface RecordedRequest {
  url: string
  method: string
  headers: Headers
  body: unknown
}

export interface FakeResponse {
  status?: number
  body?: unknown
  headers?: Record<string, string>
  /** Reject like a dropped connection instead of answering. */
  networkError?: boolean
}

type Handler = (request: RecordedRequest) => FakeResponse | Promise<FakeResponse>

export interface FakeFetch {
  mock: Mock
  requests: RecordedRequest[]
  /** Requests to one path, for example '/api/v1/auth/refresh'. */
  to: (path: string) => RecordedRequest[]
}

/** Replaces fetch with a handler so tests never touch the network. */
export function stubFetch(handler: Handler): FakeFetch {
  const requests: RecordedRequest[] = []
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof init?.body === 'string' ? init.body : undefined
    const request: RecordedRequest = {
      url: String(input),
      method: init?.method ?? 'GET',
      headers: new Headers(init?.headers),
      body: raw === undefined ? undefined : JSON.parse(raw),
    }
    requests.push(request)
    const reply = await handler(request)
    if (reply.networkError) {
      throw new TypeError('Failed to fetch')
    }
    const status = reply.status ?? 200
    const hasBody = reply.body !== undefined && status !== 204
    return new Response(hasBody ? JSON.stringify(reply.body) : null, {
      status,
      headers: { 'Content-Type': 'application/json', ...reply.headers },
    })
  })
  vi.stubGlobal('fetch', mock)
  return { mock, requests, to: (path) => requests.filter((r) => r.url.endsWith(path)) }
}

type Routes = Record<string, Handler>

/**
 * Answers by "METHOD /path". A request nobody planned for fails the test loudly, so a screen
 * cannot quietly call an endpoint the test never mentioned.
 */
export function stubApi(routes: Routes): FakeFetch {
  return stubFetch((request) => {
    const handler = routes[`${request.method} ${request.url}`]
    if (handler === undefined) {
      throw new Error(`Unexpected request: ${request.method} ${request.url}`)
    }
    return handler(request)
  })
}

/** The error shape from docs/api.md. */
export function problem(
  status: number,
  code: string,
  detail: string,
  extra: Record<string, unknown> = {},
): FakeResponse {
  return {
    status,
    body: {
      type: 'about:blank',
      title: detail,
      status,
      code,
      detail,
      request_id: 'req-12345678',
      ...extra,
    },
  }
}

export const USER = {
  id: '86076f46-9c06-4dde-b037-d4fe141d916b',
  email: 'ana@example.com',
  role: 'user',
  created_at: '2026-10-29T21:21:54.973218Z',
}

export function tokenResponse(accessToken = 'access-token-1'): FakeResponse {
  return { body: { access_token: accessToken, expires_in: 900, user: USER } }
}
