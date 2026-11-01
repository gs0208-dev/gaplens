import { Loader2 } from 'lucide-react'

import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { loadError } from '@/features/documents/errors'
import { DocumentsTable } from '@/features/documents/DocumentsTable'
import { useDocumentList } from '@/features/documents/hooks'
import { UploadDialog } from '@/features/documents/UploadDialog'

function LoadingRows() {
  return (
    <div role="status" aria-label="Loading documents" className="space-y-3">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-12 w-full" />
    </div>
  )
}

export function DocumentsPage() {
  const query = useDocumentList()
  const documents = query.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <UploadDialog />
      </div>
      <div className="mt-6">
        {query.isPending && <LoadingRows />}
        {query.isError && documents.length === 0 && (
          <ErrorState {...loadError(query.error)} onRetry={() => void query.refetch()} />
        )}
        {query.isSuccess && documents.length === 0 && (
          <p className="text-muted-foreground">
            You have no documents yet. Upload a PDF, text or Markdown file to get started.
          </p>
        )}
        {documents.length > 0 && (
          <>
            <DocumentsTable documents={documents} />
            {query.isError && (
              <div className="mt-4">
                <ErrorState {...loadError(query.error)} onRetry={() => void query.refetch()} />
              </div>
            )}
            {query.hasNextPage && (
              <div className="mt-4">
                <Button
                  variant="outline"
                  onClick={() => void query.fetchNextPage()}
                  disabled={query.isFetchingNextPage}
                >
                  {query.isFetchingNextPage && (
                    <Loader2 aria-hidden="true" className="animate-spin" />
                  )}
                  Load more
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
