import { ChevronDown, ChevronRight, Copy, Loader2 } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { KindBadge, SeverityBadge } from './badges'
import { reviewError } from './errors'
import { useSetReviewStatus } from './hooks'
import type { Finding, ReviewStatus } from './schemas'

export interface SelectedQuote {
  chunkId: string
  quote: string
}

interface Props {
  documentId: string
  finding: Finding
  selectedQuote: SelectedQuote | null
  onSelectQuote: (quote: SelectedQuote) => void
}

const REVIEW_LABELS: Record<ReviewStatus, string> = {
  open: 'Open',
  confirmed: 'Confirmed',
  dismissed: 'Dismissed',
}
const COPIED_FOR_MS = 2000

/** One finding: a header that expands to its evidence, question and review status. */
export function FindingRow({ documentId, finding, selectedQuote, onSelectQuote }: Props) {
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const dismissed = finding.review_status === 'dismissed'

  return (
    <li className="border-b last:border-b-0">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-2 py-3 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
      >
        {expanded ? (
          <ChevronDown aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        ) : (
          <ChevronRight aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        )}
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <KindBadge kind={finding.kind} />
            {finding.review_status !== 'open' && (
              <span className="text-xs text-muted-foreground">
                {REVIEW_LABELS[finding.review_status]}
              </span>
            )}
          </span>
          <span className={cn('font-medium break-words', dismissed && 'text-muted-foreground')}>
            {finding.title}
          </span>
        </span>
      </button>
      {expanded && (
        <div id={detailsId} className="space-y-4 pb-4 pl-6">
          <p className="break-words whitespace-pre-wrap">{finding.description}</p>
          <Evidence finding={finding} selectedQuote={selectedQuote} onSelectQuote={onSelectQuote} />
          <SuggestedQuestion question={finding.suggested_question} />
          <ReviewControl documentId={documentId} finding={finding} />
        </div>
      )}
    </li>
  )
}

function Evidence({ finding, selectedQuote, onSelectQuote }: Omit<Props, 'documentId'>) {
  if (finding.citations.length === 0) {
    return (
      <p className="text-muted-foreground">
        No quote: this finding is about something the document does not contain.
      </p>
    )
  }
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-muted-foreground">Evidence</h4>
      <ul className="space-y-2">
        {finding.citations.map((citation, index) => {
          const selected =
            selectedQuote?.chunkId === citation.chunk_id && selectedQuote.quote === citation.quote
          return (
            <li key={`${citation.chunk_id}-${index}`}>
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => onSelectQuote({ chunkId: citation.chunk_id, quote: citation.quote })}
                className={cn(
                  'w-full rounded-md border p-2 text-left transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none',
                  selected && 'border-primary bg-accent',
                )}
              >
                {citation.section_label !== null && (
                  <span className="block text-xs font-medium">
                    Section <span className="font-mono">{citation.section_label}</span>
                  </span>
                )}
                <span className="mt-1 block font-mono text-xs break-words whitespace-pre-wrap">
                  {citation.quote}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function SuggestedQuestion({ question }: { question: string }) {
  const [copy, setCopy] = useState<'idle' | 'copied' | 'failed'>('idle')

  useEffect(() => {
    if (copy !== 'copied') {
      return
    }
    const timer = setTimeout(() => setCopy('idle'), COPIED_FOR_MS)
    return () => clearTimeout(timer)
  }, [copy])

  async function copyQuestion() {
    try {
      await navigator.clipboard.writeText(question)
      setCopy('copied')
    } catch {
      setCopy('failed')
    }
  }

  return (
    <div className="space-y-2 rounded-md bg-secondary p-3">
      <h4 className="text-xs font-medium text-muted-foreground">Suggested question</h4>
      <p className="break-words whitespace-pre-wrap">{question}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => void copyQuestion()}>
          <Copy aria-hidden="true" />
          <span aria-live="polite">{copy === 'copied' ? 'Copied' : 'Copy question'}</span>
        </Button>
        {copy === 'failed' && (
          <p role="alert" className="text-xs text-destructive">
            Could not copy. Select the text instead.
          </p>
        )}
      </div>
    </div>
  )
}

function ReviewControl({ documentId, finding }: { documentId: string; finding: Finding }) {
  const review = useSetReviewStatus(documentId)
  const labelId = useId()
  const failure = review.isError ? reviewError(review.error) : null

  return (
    <div className="space-y-2">
      <h4 id={labelId} className="text-xs font-medium text-muted-foreground">
        Review status
      </h4>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {(Object.keys(REVIEW_LABELS) as ReviewStatus[]).map((status) => {
          const pressed = finding.review_status === status
          return (
            <Button
              key={status}
              variant="outline"
              size="sm"
              aria-pressed={pressed}
              disabled={review.isPending}
              className={cn(pressed && 'border-primary bg-accent')}
              onClick={() => {
                if (!pressed) {
                  review.mutate({ findingId: finding.id, status })
                }
              }}
            >
              {review.isPending && review.variables.status === status && (
                <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
              )}
              {REVIEW_LABELS[status]}
            </Button>
          )
        })}
      </div>
      {failure !== null && (
        <p role="alert" className="text-xs text-destructive">
          {failure.message}
          {failure.requestId !== null && (
            <span className="mt-1 block text-muted-foreground">
              Request id: {failure.requestId}
            </span>
          )}
        </p>
      )}
    </div>
  )
}
