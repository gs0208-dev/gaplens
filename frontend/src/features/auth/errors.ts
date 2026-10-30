import { ApiError } from '@/lib/api'

export interface DescribedError {
  /** A sentence for the error summary at the top of the form, or null when fields say it all. */
  message: string | null
  requestId: string | null
  fieldErrors: { email?: string; password?: string }
}

/** Registering worked, but the sign-in that follows it did not. */
export class AccountCreatedError extends Error {
  constructor(readonly reason: unknown) {
    super('The account was created, but signing in failed.')
    this.name = 'AccountCreatedError'
  }
}

function describeWait(seconds: number | null): string {
  if (seconds === null) {
    return 'a few minutes'
  }
  if (seconds < 60) {
    return seconds === 1 ? '1 second' : `${seconds} seconds`
  }
  const minutes = Math.ceil(seconds / 60)
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}

/** Turns a failure into text a person can act on. The server's own message is safe to show. */
export function describeError(error: unknown): DescribedError {
  if (error instanceof AccountCreatedError) {
    return {
      message: 'Your account was created, but signing in failed. Sign in with your new details.',
      requestId: error.reason instanceof ApiError ? error.reason.requestId : null,
      fieldErrors: {},
    }
  }
  if (!(error instanceof ApiError)) {
    return { message: 'Something went wrong. Try again.', requestId: null, fieldErrors: {} }
  }

  const base = { requestId: error.requestId, fieldErrors: {} }
  switch (error.code) {
    case 'network_error':
      return {
        ...base,
        message: 'Could not reach the server. Check your connection and try again.',
      }
    case 'rate_limited':
      return {
        ...base,
        message: `Too many attempts. Try again in ${describeWait(error.retryAfterSeconds)}.`,
      }
    case 'email_already_registered':
      return { ...base, message: null, fieldErrors: { email: error.detail } }
    case 'validation_error':
      return describeValidationError(error)
    default:
      return { ...base, message: error.detail }
  }
}

function describeValidationError(error: ApiError): DescribedError {
  const fieldErrors: DescribedError['fieldErrors'] = {}
  let unplaced = error.fieldErrors.length === 0
  for (const { field, message } of error.fieldErrors) {
    if (field === 'email' || field === 'password') {
      fieldErrors[field] = message
    } else {
      unplaced = true
    }
  }
  return {
    message: unplaced ? error.detail : null,
    requestId: error.requestId,
    fieldErrors,
  }
}
