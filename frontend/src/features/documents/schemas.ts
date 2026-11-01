import { z } from 'zod'

// The response shapes from docs/api.md. apiRequest refuses anything that does not match.

export const documentStatusSchema = z.enum(['uploaded', 'processing', 'ready', 'failed'])
export type DocumentStatus = z.infer<typeof documentStatusSchema>

export const documentSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  status: documentStatusSchema,
  page_count: z.number().nullable(),
  chunk_count: z.number(),
  created_at: z.string(),
})
export type DocumentSummary = z.infer<typeof documentSummarySchema>

export const documentPageSchema = z.object({
  items: z.array(documentSummarySchema),
  next_cursor: z.string().nullable(),
})

export const documentSchema = documentSummarySchema.extend({
  filename: z.string(),
  mime_type: z.string(),
  size_bytes: z.number(),
  error_message: z.string().nullable(),
})
export type DocumentDetails = z.infer<typeof documentSchema>

export const documentResponseSchema = z.object({ document: documentSchema })

export const chunkSchema = z.object({
  id: z.string(),
  chunk_index: z.number(),
  section_label: z.string().nullable(),
  heading: z.string().nullable(),
  content: z.string(),
  page_start: z.number().nullable(),
})
export type Chunk = z.infer<typeof chunkSchema>

export const chunkListSchema = z.object({ items: z.array(chunkSchema) })

/** A document the server is still working on. The client keeps asking until this is false. */
export function isInProgress(status: DocumentStatus): boolean {
  return status === 'uploaded' || status === 'processing'
}
