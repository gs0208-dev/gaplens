import { ApiError, apiRequest } from '@/lib/api'

import {
  analysisResponseSchema,
  findingResponseSchema,
  type Analysis,
  type Finding,
  type ReviewStatus,
} from './schemas'

/** The newest report of a document, or null when none has been made yet. */
export async function getLatestReport(documentId: string): Promise<Analysis | null> {
  try {
    const { analysis } = await apiRequest(`/documents/${documentId}/analyses/latest`, {
      schema: analysisResponseSchema,
    })
    return analysis
  } catch (error) {
    if (error instanceof ApiError && error.code === 'analysis_not_found') {
      return null
    }
    throw error
  }
}

export async function startReport(documentId: string): Promise<Analysis> {
  const { analysis } = await apiRequest(`/documents/${documentId}/analyses`, {
    method: 'POST',
    schema: analysisResponseSchema,
  })
  return analysis
}

export async function setReviewStatus(
  findingId: string,
  reviewStatus: ReviewStatus,
): Promise<Finding> {
  const { finding } = await apiRequest(`/findings/${findingId}`, {
    method: 'PATCH',
    body: { review_status: reviewStatus },
    schema: findingResponseSchema,
  })
  return finding
}
