import { ApiError } from '@/lib/api'
import { formatWait } from '@/lib/format'

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024

export interface ShownError {
  message: string
  /** Quoted in small text so a user can give it to whoever looks into the problem. */
  requestId: string | null
}

const UPLOAD_MESSAGES: Record<string, string> = {
  file_too_large: 'This file is larger than 5 MB.',
  unsupported_file_type: 'Upload a PDF, a plain text file or a Markdown file.',
  encrypted_pdf: 'This PDF is password protected. Remove the protection and upload it again.',
  pdf_unreadable: 'This PDF is damaged or uses a format that cannot be read.',
  too_many_pages: 'This document has more than 100 pages.',
  text_too_long: 'This document has more than 300,000 characters of text.',
  no_extractable_text: 'No text could be read from this file. Scanned documents are not supported.',
  duplicate_document:
    'You have already uploaded this file. Delete the earlier one to upload it again.',
  network_error: 'Could not reach the server. Check your connection and try again.',
}

/** What to tell the user when an upload is refused. Only plain sentences, never server text. */
export function uploadError(error: unknown): ShownError {
  if (!(error instanceof ApiError)) {
    return { message: 'The upload failed. Try again.', requestId: null }
  }
  if (error.code === 'rate_limited') {
    return {
      message: `You have uploaded too many documents. Try again in ${formatWait(error.retryAfterSeconds)}.`,
      requestId: error.requestId,
    }
  }
  if (error.code === 'validation_error') {
    return { message: 'The title can be at most 200 characters.', requestId: error.requestId }
  }
  return {
    message: UPLOAD_MESSAGES[error.code] ?? 'The upload failed. Try again.',
    requestId: error.requestId,
  }
}

/** What to tell the user when something else on the documents screens fails. */
export function loadError(error: unknown): ShownError {
  if (error instanceof ApiError && error.code === 'network_error') {
    return {
      message: 'Could not reach the server. Check your connection and try again.',
      requestId: null,
    }
  }
  return {
    message: 'The documents could not be loaded. Try again.',
    requestId: error instanceof ApiError ? error.requestId : null,
  }
}
