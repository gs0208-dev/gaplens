import { z } from 'zod'

// The analysis shapes from docs/api.md. apiRequest refuses anything that does not match.

export const severitySchema = z.enum(['high', 'medium', 'low'])
export type Severity = z.infer<typeof severitySchema>

export const kindSchema = z.enum(['missing', 'unclear', 'contradiction'])
export type Kind = z.infer<typeof kindSchema>

export const reviewStatusSchema = z.enum(['open', 'confirmed', 'dismissed'])
export type ReviewStatus = z.infer<typeof reviewStatusSchema>

export const findingCitationSchema = z.object({
  chunk_id: z.string(),
  section_label: z.string().nullable(),
  quote: z.string(),
})
export type FindingCitation = z.infer<typeof findingCitationSchema>

export const findingSchema = z.object({
  id: z.string(),
  kind: kindSchema,
  severity: severitySchema,
  title: z.string(),
  description: z.string(),
  suggested_question: z.string(),
  review_status: reviewStatusSchema,
  citations: z.array(findingCitationSchema),
})
export type Finding = z.infer<typeof findingSchema>

export const analysisSchema = z.object({
  id: z.string(),
  document_id: z.string(),
  status: z.enum(['queued', 'running', 'succeeded', 'failed']),
  summary: z.string().nullable(),
  findings_count: z.number(),
  dropped_findings_count: z.number(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  findings: z.array(findingSchema),
})
export type Analysis = z.infer<typeof analysisSchema>

export const analysisResponseSchema = z.object({ analysis: analysisSchema })
export const findingResponseSchema = z.object({ finding: findingSchema })

export function isRunning(analysis: Analysis | null | undefined): boolean {
  return analysis?.status === 'queued' || analysis?.status === 'running'
}
