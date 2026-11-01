import { z } from 'zod'

export const citationSchema = z.object({
  chunk_id: z.string(),
  section_label: z.string().nullable(),
  quote: z.string(),
})
export type Citation = z.infer<typeof citationSchema>

export const messageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  grounded: z.boolean().nullable(),
  citations: z.array(citationSchema),
  created_at: z.string(),
})
export type ChatMessage = z.infer<typeof messageSchema>

export const messagePageSchema = z.object({
  items: z.array(messageSchema),
  next_cursor: z.string().nullable(),
})

export const chatResponseSchema = z.object({
  thread_id: z.string(),
  message: messageSchema,
})

export const threadPageSchema = z.object({
  items: z.array(
    z.object({
      id: z.string(),
      title: z.string().nullable(),
      created_at: z.string(),
      updated_at: z.string(),
    }),
  ),
  next_cursor: z.string().nullable(),
})
