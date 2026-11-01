import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { latestThreadId, listMessages, sendQuestion } from './api'

export function useLatestThread(documentId: string) {
  return useQuery({
    queryKey: ['threads', documentId, 'latest'],
    queryFn: () => latestThreadId(documentId),
  })
}

/** Every message of a thread, oldest first. Follows the cursor until there is no next page. */
export function useThreadMessages(threadId: string | null) {
  const query = useInfiniteQuery({
    queryKey: ['messages', threadId],
    queryFn: ({ pageParam }) => listMessages(threadId ?? '', pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: threadId !== null,
  })
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])
  return { ...query, messages: query.data?.pages.flatMap((page) => page.items) ?? [] }
}

export function useSendQuestion(documentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ question, threadId }: { question: string; threadId: string | null }) =>
      sendQuestion(documentId, question, threadId),
    // Waits for the messages to be read again, so the answer appears together with the question
    // that was shown while it was being written.
    onSuccess: async (reply) => {
      await queryClient.invalidateQueries({ queryKey: ['messages', reply.thread_id] })
      await queryClient.invalidateQueries({ queryKey: ['threads', documentId] })
    },
  })
}
