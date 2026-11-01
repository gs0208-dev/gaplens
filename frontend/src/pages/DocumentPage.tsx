import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { DocumentText } from '@/features/documents/DocumentText'
import { loadError } from '@/features/documents/errors'
import { useChunks, useDocument } from '@/features/documents/hooks'
import { StatusBadge } from '@/features/documents/StatusBadge'
import { ApiError } from '@/lib/api'

function BackLink() {
  return (
    <Link
      to="/documents"
      className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      Documents
    </Link>
  )
}

function WorkspaceSkeleton() {
  return (
    <div role="status" aria-label="Loading the document" className="space-y-4">
      <Skeleton className="h-8 w-1/2" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  )
}

export function DocumentPage() {
  const { documentId = '' } = useParams()
  const document = useDocument(documentId)
  const status = document.data?.status
  const chunks = useChunks(documentId, status === 'ready')
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null)
  const [pane, setPane] = useState('chat')

  if (document.isPending) {
    return <WorkspaceSkeleton />
  }
  if (document.isError) {
    if (document.error instanceof ApiError && document.error.status === 404) {
      return (
        <div className="space-y-4">
          <BackLink />
          <h1 className="text-2xl font-semibold">Document not found</h1>
          <p className="text-muted-foreground">This document does not exist or has been deleted.</p>
        </div>
      )
    }
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorState {...loadError(document.error)} onRetry={() => void document.refetch()} />
      </div>
    )
  }

  const details = document.data

  function selectCitation(chunkId: string) {
    setSelectedChunkId(chunkId)
    // On a narrow screen the text is on another tab, so go there to show the section.
    setPane('document')
  }

  let text
  if (details.status === 'ready') {
    if (chunks.isPending) {
      text = (
        <div role="status" aria-label="Loading the text" className="space-y-3">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )
    } else if (chunks.isError) {
      text = <ErrorState {...loadError(chunks.error)} onRetry={() => void chunks.refetch()} />
    } else {
      text = <DocumentText chunks={chunks.data} highlightedChunkId={selectedChunkId} />
    }
  } else if (details.status === 'failed') {
    text = (
      <ErrorState
        message={details.error_message ?? 'This document could not be processed. Upload it again.'}
      />
    )
  } else {
    text = (
      <p className="text-muted-foreground">
        The document is being processed. Its text appears here when it is ready.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <BackLink />
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold break-words">{details.title}</h1>
        <StatusBadge status={details.status} />
      </div>
      <Tabs value={pane} onValueChange={setPane} className="gap-4">
        <TabsList className="lg:hidden">
          <TabsTrigger value="document">Document</TabsTrigger>
          <TabsTrigger value="chat">Chat</TabsTrigger>
        </TabsList>
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Both panes stay in the page. Below 1024 px the tabs show one at a time; from 1024 px
              up both are shown side by side, whatever the tabs say. */}
          <TabsContent
            value="document"
            forceMount
            className="lg:block! lg:max-h-[75vh] lg:overflow-y-auto"
          >
            <h2 className="mb-3 hidden text-xl font-semibold lg:block">Document</h2>
            {text}
          </TabsContent>
          <TabsContent value="chat" forceMount className="lg:block! lg:max-h-[75vh]">
            <ChatPanel
              documentId={details.id}
              status={details.status}
              selectedChunkId={selectedChunkId}
              onSelectCitation={selectCitation}
            />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
