import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { DocumentText, type Highlight } from '@/features/documents/DocumentText'
import { loadError } from '@/features/documents/errors'
import { useChunks, useDocument } from '@/features/documents/hooks'
import { StatusBadge } from '@/features/documents/StatusBadge'
import { ReportPanel } from '@/features/report/ReportPanel'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

type Pane = 'document' | 'report' | 'chat'
type SidePane = 'report' | 'chat'

// Matches Tailwind's lg breakpoint. Without matchMedia (tests, old browsers) it counts as narrow.
function isNarrow(): boolean {
  return (
    typeof window.matchMedia !== 'function' || !window.matchMedia('(min-width: 1024px)').matches
  )
}

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
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  // pane is the tab shown on a narrow screen; side is what the right pane shows on a wide one.
  const [pane, setPane] = useState<Pane>('report')
  const [side, setSide] = useState<SidePane>('report')

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

  function show(next: Highlight) {
    setHighlight(next)
    // On a narrow screen the text is on another tab, so go there to show the section.
    if (isNarrow()) {
      setPane('document')
    }
  }

  function changePane(next: string) {
    if (next === 'document' || next === 'report' || next === 'chat') {
      setPane(next)
      if (next !== 'document') {
        setSide(next)
      }
    }
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
      text = <DocumentText chunks={chunks.data} highlight={highlight} />
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
      <Tabs value={pane} onValueChange={changePane} className="gap-4">
        {/* One grid for both widths. Below 1024 px the tabs show one pane at a time; from 1024 px
            up the document is always on the left and the tabs choose the right pane. */}
        <div className="grid gap-4 lg:grid-cols-2 lg:gap-x-6">
          <TabsList className="lg:col-start-2 lg:row-start-1">
            <TabsTrigger value="document" className="lg:hidden">
              Document
            </TabsTrigger>
            <TabsTrigger value="report">Report</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
          </TabsList>
          <TabsContent
            value="document"
            forceMount
            className="lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:block! lg:max-h-[75vh] lg:overflow-y-auto"
          >
            <h2 className="mb-3 hidden text-xl font-semibold lg:block">Document</h2>
            {text}
          </TabsContent>
          <TabsContent
            value="report"
            forceMount
            className={cn(
              'lg:col-start-2 lg:row-start-2 lg:max-h-[75vh] lg:overflow-y-auto',
              pane === 'document' && side === 'report' && 'lg:block!',
            )}
          >
            <ReportPanel
              documentId={details.id}
              status={details.status}
              selectedQuote={
                highlight?.quote ? { chunkId: highlight.chunkId, quote: highlight.quote } : null
              }
              onSelectQuote={(quote) => show(quote)}
            />
          </TabsContent>
          <TabsContent
            value="chat"
            forceMount
            className={cn(
              'lg:col-start-2 lg:row-start-2 lg:max-h-[75vh]',
              pane === 'document' && side === 'chat' && 'lg:block!',
            )}
          >
            <ChatPanel
              documentId={details.id}
              status={details.status}
              selectedChunkId={highlight?.quote === null ? highlight.chunkId : null}
              onSelectCitation={(chunkId) => show({ chunkId, quote: null })}
            />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
