import { apiRequest } from '@/lib/api'

import { chatResponseSchema, messagePageSchema, threadPageSchema } from './schemas'

/** The id of the conversation used last, or null if the document has none yet. */
export async function latestThreadId(documentId: string): Promise<string | null> {
  const page = await apiRequest(`/documents/${documentId}/threads?limit=1`, {
    schema: threadPageSchema,
  })
  return page.items[0]?.id ?? null
}

export function listMessages(threadId: string, cursor: string | null) {
  const query = new URLSearchParams({ limit: '100' })
  if (cursor !== null) {
    query.set('cursor', cursor)
  }
  return apiRequest(`/threads/${threadId}/messages?${query.toString()}`, {
    schema: messagePageSchema,
  })
}

export function sendQuestion(documentId: string, question: string, threadId: string | null) {
  return apiRequest(`/documents/${documentId}/chat`, {
    method: 'POST',
    body: threadId === null ? { question } : { question, thread_id: threadId },
    schema: chatResponseSchema,
  })
}
