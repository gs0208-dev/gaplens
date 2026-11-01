import { apiRequest } from '@/lib/api'

import {
  chunkListSchema,
  documentPageSchema,
  documentResponseSchema,
  type DocumentDetails,
} from './schemas'

export const PAGE_SIZE = 20

export function listDocuments(cursor: string | null) {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) })
  if (cursor !== null) {
    query.set('cursor', cursor)
  }
  return apiRequest(`/documents?${query.toString()}`, { schema: documentPageSchema })
}

export async function getDocument(documentId: string): Promise<DocumentDetails> {
  const { document } = await apiRequest(`/documents/${documentId}`, {
    schema: documentResponseSchema,
  })
  return document
}

export async function listChunks(documentId: string) {
  const { items } = await apiRequest(`/documents/${documentId}/chunks`, {
    schema: chunkListSchema,
  })
  return items
}

export async function uploadDocument(file: File, title: string): Promise<DocumentDetails> {
  const form = new FormData()
  form.append('file', file)
  if (title.trim() !== '') {
    form.append('title', title.trim())
  }
  const { document } = await apiRequest('/documents', {
    method: 'POST',
    body: form,
    schema: documentResponseSchema,
  })
  return document
}

export function deleteDocument(documentId: string) {
  return apiRequest(`/documents/${documentId}`, { method: 'DELETE' })
}
