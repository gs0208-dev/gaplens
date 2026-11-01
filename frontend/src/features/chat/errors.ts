import { ApiError } from '@/lib/api'
import { formatWait } from '@/lib/format'

export const MAX_QUESTION_LENGTH = 1000

export interface ChatErrorView {
  message: string
  requestId: string | null
  /** The saved conversation is gone, so the next question has to start a new one. */
  startNewThread: boolean
}

const MESSAGES: Record<string, string> = {
  document_not_ready: 'This document is still being processed. Try again when it is ready.',
  document_not_found: 'This document no longer exists.',
  thread_not_found:
    'That conversation no longer exists. Send the question again to start a new one.',
  llm_unavailable: 'Answers are not available right now. Try again later.',
  llm_timeout: 'The answer took too long. Try again.',
  llm_invalid_output: 'An answer could not be produced. Try again.',
  validation_error: 'A question can be 1 to 1,000 characters long.',
  network_error: 'Could not reach the server. Check your connection and try again.',
}

/** What to tell the user when a question fails. Plain sentences, never server text. */
export function chatError(error: unknown): ChatErrorView {
  if (!(error instanceof ApiError)) {
    return {
      message: 'The question could not be sent. Try again.',
      requestId: null,
      startNewThread: false,
    }
  }
  const message =
    error.code === 'rate_limited'
      ? `You have asked too many questions. Try again in ${formatWait(error.retryAfterSeconds)}.`
      : (MESSAGES[error.code] ?? 'The question could not be answered. Try again.')
  return {
    message,
    requestId: error.requestId,
    startNewThread: error.code === 'thread_not_found',
  }
}
