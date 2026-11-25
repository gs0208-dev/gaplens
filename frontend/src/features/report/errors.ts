import { ApiError } from '@/lib/api'
import { formatWait } from '@/lib/format'

import type { ShownError } from '@/features/documents/errors'

const START_MESSAGES: Record<string, string> = {
  document_not_ready: 'This document is still being processed. Try again when it is ready.',
  document_not_found: 'This document no longer exists.',
  network_error: 'Could not reach the server. Check your connection and try again.',
}

/** What to tell the user when a report cannot be started. Plain sentences, never server text. */
export function startError(error: unknown): ShownError {
  if (!(error instanceof ApiError)) {
    return { message: 'The report could not be started. Try again.', requestId: null }
  }
  if (error.code === 'rate_limited') {
    return {
      message: `You have started too many reports. Try again in ${formatWait(error.retryAfterSeconds)}.`,
      requestId: error.requestId,
    }
  }
  if (error.code === 'daily_budget_exceeded') {
    return {
      message: `You have reached today's limit for answers and reports. Try again in ${formatWait(error.retryAfterSeconds)}.`,
      requestId: error.requestId,
    }
  }
  return {
    message: START_MESSAGES[error.code] ?? 'The report could not be started. Try again.',
    requestId: error.requestId,
  }
}

export function reportLoadError(error: unknown): ShownError {
  if (error instanceof ApiError && error.code === 'network_error') {
    return {
      message: 'Could not reach the server. Check your connection and try again.',
      requestId: null,
    }
  }
  return {
    message: 'The report could not be loaded. Try again.',
    requestId: error instanceof ApiError ? error.requestId : null,
  }
}

export function reviewError(error: unknown): ShownError {
  if (error instanceof ApiError && error.code === 'finding_not_found') {
    return {
      message: 'This finding no longer exists. Reload the report.',
      requestId: error.requestId,
    }
  }
  return {
    message: 'The status could not be saved. Try again.',
    requestId: error instanceof ApiError ? error.requestId : null,
  }
}
