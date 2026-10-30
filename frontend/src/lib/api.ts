import { z, type ZodType } from 'zod'

// The only place in the app that calls fetch. Components and hooks go through apiRequest.

const API_PREFIX = '/api/v1'

export interface FieldError {
  field: string
  message: string
}

interface ApiErrorDetails {
  status: number
  code: string
  detail: string
  requestId: string | null
  fieldErrors: FieldError[]
  retryAfterSeconds: number | null
}

/** An error response in the format from docs/api.md, or a failure to get one at all. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly requestId: string | null
  readonly fieldErrors: FieldError[]
  readonly retryAfterSeconds: number | null

  constructor(details: ApiErrorDetails) {
    super(details.detail)
    this.name = 'ApiError'
    this.status = details.status
    this.code = details.code
    this.detail = details.detail
    this.requestId = details.requestId
    this.fieldErrors = details.fieldErrors
    this.retryAfterSeconds = details.retryAfterSeconds
  }
}

/**
 * What the client needs to know about the session. It is a port so that this file does not
 * import from the auth feature, which itself uses this file.
 */
export interface SessionPort {
  getAccessToken: () => string | null
  /** Gets a new access token. Resolves to false when there is no session to continue. */
  refresh: () => Promise<boolean>
}

let sessionPort: SessionPort = { getAccessToken: () => null, refresh: async () => false }

export function setSessionPort(port: SessionPort): void {
  sessionPort = port
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  /** False for calls that must not carry the access token, such as login and refresh. */
  auth?: boolean
}

const problemSchema = z.object({
  code: z.string(),
  detail: z.string(),
  request_id: z.string().nullish(),
  errors: z.array(z.object({ field: z.string(), message: z.string() })).optional(),
})

export async function apiRequest<T>(
  path: string,
  options: RequestOptions & { schema: ZodType<T> },
): Promise<T>
export async function apiRequest(path: string, options?: RequestOptions): Promise<void>
export async function apiRequest(
  path: string,
  options: RequestOptions & { schema?: ZodType } = {},
): Promise<unknown> {
  const { auth = true } = options
  try {
    return await send(path, options, auth ? sessionPort.getAccessToken() : null)
  } catch (error) {
    if (!auth || !isExpiredAccessToken(error) || !(await sessionPort.refresh())) {
      throw error
    }
    // One retry only. If the new token is rejected too, that error goes to the caller.
    return send(path, options, sessionPort.getAccessToken())
  }
}

function isExpiredAccessToken(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.code === 'invalid_access_token'
}

async function send(
  path: string,
  options: RequestOptions & { schema?: ZodType },
  accessToken: string | null,
): Promise<unknown> {
  const headers = new Headers()
  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (accessToken !== null) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  let response: Response
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      detail: 'Could not reach the server.',
      requestId: null,
      fieldErrors: [],
      retryAfterSeconds: null,
    })
  }

  if (!response.ok) {
    throw await toApiError(response)
  }
  if (options.schema === undefined || response.status === 204) {
    return undefined
  }

  const parsed = options.schema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    // The server answered, but not in the shape we were promised. Never pass that along as data.
    throw new ApiError({
      status: response.status,
      code: 'invalid_response',
      detail: 'The server returned an unexpected response.',
      requestId: response.headers.get('X-Request-ID'),
      fieldErrors: [],
      retryAfterSeconds: null,
    })
  }
  return parsed.data
}

async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = Number.parseInt(response.headers.get('Retry-After') ?? '', 10)
  const retryAfterSeconds = Number.isFinite(retryAfter) ? retryAfter : null

  const problem = problemSchema.safeParse(await response.json().catch(() => null))
  if (!problem.success) {
    // A proxy error page or anything else that is not our format. Its text is not shown.
    return new ApiError({
      status: response.status,
      code: 'unexpected_response',
      detail: 'The server returned an unexpected response.',
      requestId: null,
      fieldErrors: [],
      retryAfterSeconds,
    })
  }
  return new ApiError({
    status: response.status,
    code: problem.data.code,
    detail: problem.data.detail,
    requestId: problem.data.request_id ?? null,
    fieldErrors: problem.data.errors ?? [],
    retryAfterSeconds,
  })
}
