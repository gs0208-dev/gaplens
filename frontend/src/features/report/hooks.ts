import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { POLL_INTERVAL_MS } from '@/features/documents/hooks'

import { getLatestReport, setReviewStatus, startReport } from './api'
import { isRunning, type Analysis, type ReviewStatus } from './schemas'

const reportKey = (documentId: string) => ['report', documentId] as const

/** The latest report, polled while it is queued or running. */
export function useLatestReport(documentId: string, ready: boolean) {
  return useQuery({
    queryKey: reportKey(documentId),
    queryFn: () => getLatestReport(documentId),
    enabled: ready,
    refetchInterval: (query) => (isRunning(query.state.data) ? POLL_INTERVAL_MS : false),
  })
}

export function useStartReport(documentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => startReport(documentId),
    // The queued report goes straight into the cache, which starts the polling.
    onSuccess: (analysis) => queryClient.setQueryData(reportKey(documentId), analysis),
  })
}

export function useSetReviewStatus(documentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ findingId, status }: { findingId: string; status: ReviewStatus }) =>
      setReviewStatus(findingId, status),
    onSuccess: (finding) =>
      queryClient.setQueryData<Analysis | null>(reportKey(documentId), (report) =>
        report
          ? { ...report, findings: report.findings.map((f) => (f.id === finding.id ? finding : f)) }
          : report,
      ),
  })
}
