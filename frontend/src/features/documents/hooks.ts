import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { deleteDocument, getDocument, listChunks, listDocuments, uploadDocument } from './api'
import { isInProgress } from './schemas'

/** docs/api.md: poll every 2 seconds until the document is ready or failed. */
export const POLL_INTERVAL_MS = 2000

export function useDocumentList() {
  return useInfiniteQuery({
    queryKey: ['documents'],
    queryFn: ({ pageParam }) => listDocuments(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    // Only while something is still being processed. A list of finished documents is left alone.
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) => page.items.some((item) => isInProgress(item.status)))
        ? POLL_INTERVAL_MS
        : false,
  })
}

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ['document', documentId],
    queryFn: () => getDocument(documentId),
    refetchInterval: (query) =>
      query.state.data && isInProgress(query.state.data.status) ? POLL_INTERVAL_MS : false,
  })
}

/** The text of a document. Asked for only once the document is ready; before that it is a 409. */
export function useChunks(documentId: string, ready: boolean) {
  return useQuery({
    queryKey: ['chunks', documentId],
    queryFn: () => listChunks(documentId),
    enabled: ready,
    staleTime: Infinity,
  })
}

export function useUploadDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, title }: { file: File; title: string }) => uploadDocument(file, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  })
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: (_result, documentId) => {
      queryClient.removeQueries({ queryKey: ['document', documentId] })
      queryClient.removeQueries({ queryKey: ['chunks', documentId] })
      return queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}
